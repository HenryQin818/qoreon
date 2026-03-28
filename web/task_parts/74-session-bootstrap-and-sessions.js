    function channelDialogType(channelName) {
      const ch = String(channelName || "").trim();
      if (/主体-总控/.test(ch)) return { full: "主对话", short: "主" };
      return { full: "子级对话", short: "子级" };
    }

    function buildBootstrapVisibleMessages(channelName) {
      const ch = String(channelName || "").trim() || "当前通道";
      const dialog = channelDialogType(ch);
      const msg1 = "[Qoreon] " + ch + "（" + dialog.full + "）";
      const msg2 = "【连通性验收】通道：" + ch + "；对话类型：" + dialog.full + "。请仅回复：OK（" + ch + "-" + dialog.short + "）";
      return [msg1, msg2];
    }

    async function dedupChannelSessions(projectId, channelName, keepSessionId) {
      try {
        const r = await fetch("/api/sessions/dedup", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            project_id: String(projectId || ""),
            channel_name: String(channelName || ""),
            keep_session_id: String(keepSessionId || ""),
            strategy: "latest",
          }),
        });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) return { ok: false, removedCount: 0, error: String((j && (j.error || j.message)) || "请求失败") };
        const result = (j && j.result) || {};
        return {
          ok: true,
          removedCount: Number(result.removed_count || 0),
          keptSessionId: String(result.kept_session_id || ""),
          error: "",
        };
      } catch (_) {
        return { ok: false, removedCount: 0, error: "网络或服务异常" };
      }
    }

    async function verifySessionBindingVisibility(projectId, channelName, sessionId) {
      try {
        const r = await fetch("/api/dashboard/visibility-check", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            project_id: String(projectId || ""),
            channel_name: String(channelName || ""),
            session_id: String(sessionId || ""),
            expected_generated_at: String((DATA && DATA.generated_at) || ""),
            auto_rebuild: true,
          }),
        });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) {
          return { ok: false, hardRefreshRequired: false, error: String((j && (j.error || j.message)) || "请求失败") };
        }
        const action = (j && j.action) || {};
        return {
          ok: true,
          hardRefreshRequired: !!action.hard_refresh_required,
          rebuildTriggered: !!action.rebuild_triggered,
          reason: String(action.reason || ""),
          error: "",
        };
      } catch (_) {
        return { ok: false, hardRefreshRequired: false, error: "网络或服务异常" };
      }
    }

    async function tryUpdateSessionModel(sessionId, model) {
      const sid = String(sessionId || "").trim();
      const normalized = normalizeSessionModel(model);
      if (!looksLikeSessionId(sid) || !normalized) return false;
      try {
        const r = await fetch("/api/sessions/" + encodeURIComponent(sid), {
          method: "PUT",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ model: normalized }),
        });
        return !!(r && r.ok);
      } catch (_) {
        return false;
      }
    }

    function resolveConversationSessionPresentation(raw, channelName, sessionId) {
      const alias = String((raw && raw.alias) || "").trim();
      const channel = String(channelName || "").trim();
      const sid = String(sessionId || "").trim();
      const explicitDisplayChannel = String(
        (raw && (
          raw.displayChannel ||
          raw.display_channel ||
          raw.display_name
        )) || ""
      ).trim();
      const explicitDisplayName = String(
        (raw && (
          raw.displayName ||
          raw.display_name ||
          raw.displayChannel ||
          raw.display_channel
        )) || ""
      ).trim();
      let displayNameSource = String(
        (raw && (
          raw.displayNameSource ||
          raw.display_name_source
        )) || ""
      ).trim();
      const displayChannel = alias || explicitDisplayChannel || channel || sid;
      const displayName = alias || explicitDisplayName || displayChannel || channel || sid;
      if (alias) displayNameSource = "alias";
      else if (!displayNameSource && explicitDisplayName) displayNameSource = "display_name";
      else if (!displayNameSource && channel) displayNameSource = "channel_name";
      else if (!displayNameSource && sid) displayNameSource = "session_id";
      return {
        alias,
        displayChannel,
        displayName,
        displayNameSource,
      };
    }

    function ensureConversationSessionDirectoryStateMaps() {
      if (!PCONV.sessionDirectoryByProject || typeof PCONV.sessionDirectoryByProject !== "object") {
        PCONV.sessionDirectoryByProject = Object.create(null);
      }
      if (!PCONV.sessionDirectoryMetaByProject || typeof PCONV.sessionDirectoryMetaByProject !== "object") {
        PCONV.sessionDirectoryMetaByProject = Object.create(null);
      }
      if (!PCONV.sessionDirectoryPromiseByProject || typeof PCONV.sessionDirectoryPromiseByProject !== "object") {
        PCONV.sessionDirectoryPromiseByProject = Object.create(null);
      }
    }

    function markConversationSessionDirectoryMeta(projectId, extra = {}) {
      const pid = String(projectId || "").trim();
      if (!pid) return;
      ensureConversationSessionDirectoryStateMaps();
      const current = (PCONV.sessionDirectoryMetaByProject && PCONV.sessionDirectoryMetaByProject[pid]) || {};
      PCONV.sessionDirectoryMetaByProject[pid] = {
        ...current,
        ...extra,
        liveLoaded: extra && Object.prototype.hasOwnProperty.call(extra, "liveLoaded")
          ? !!extra.liveLoaded
          : !!current.liveLoaded,
        loadedAt: String((extra && extra.loadedAt) || current.loadedAt || new Date().toISOString()),
        source: String((extra && extra.source) || current.source || ""),
        error: String((extra && extra.error) || ""),
      };
    }

    function formatConversationSessionsFromApi(projectId, sessions) {
      const pid = String(projectId || "").trim();
      return (Array.isArray(sessions) ? sessions : []).map((s) => {
        const sid = firstNonEmptyText([s.id, s.session_id, s.sessionId]);
        const channelName = String(s.channel_name || "");
        const presentation = resolveConversationSessionPresentation(s, channelName, sid);
        const runtimeState = normalizeRuntimeState(s.runtime_state || s.runtimeState || null);
        const latestRunSummary = normalizeLatestRunSummary(s.latest_run_summary || s.latestRunSummary || null);
        const sessionDisplayState = normalizeDisplayState(
          firstNonEmptyText([s.session_display_state, s.sessionDisplayState, runtimeState.display_state]) || "idle",
          "idle"
        );
        const rawHeartbeat = (s.heartbeat && typeof s.heartbeat === "object") ? s.heartbeat : {};
        const heartbeatItems = Array.isArray(rawHeartbeat.items)
          ? normalizeHeartbeatTaskItemsClient(rawHeartbeat.items, pid, rawHeartbeat)
          : [];
        const heartbeatSummary = normalizeHeartbeatSummaryClient(
          s.heartbeat_summary || s.heartbeatSummary || rawHeartbeat.summary || {},
          heartbeatItems
        );
        return {
          sessionId: String(sid || ""),
          id: String(sid || ""),
          project_id: pid,
          channel_name: channelName,
          environment: String(s.environment || "stable"),
          worktree_root: String(s.worktree_root || s.worktreeRoot || ""),
          workdir: String(s.workdir || ""),
          branch: String(s.branch || ""),
          primaryChannel: channelName,
          channels: [channelName],
          alias: presentation.alias,
          displayChannel: presentation.displayChannel,
          displayName: presentation.displayName,
          displayNameSource: presentation.displayNameSource,
          codexTitle: String(s.codex_title || ""),
          cli_type: String(s.cli_type || "codex"),
          model: normalizeSessionModel(s.model),
          reasoning_effort: normalizeReasoningEffort(s.reasoning_effort || s.reasoningEffort),
          status: String(s.status || "active"),
          created_at: String(s.created_at || ""),
          last_used_at: String(s.last_used_at || ""),
          is_primary: !!s.is_primary,
          source: String(s.source || ""),
          lastActiveAt: String(s.lastActiveAt || latestRunSummary.updated_at || s.last_used_at || ""),
          lastStatus: sessionDisplayState,
          lastPreview: String(s.lastPreview || latestRunSummary.preview || ""),
          lastTimeout: false,
          lastError: String(s.lastError || latestRunSummary.error || ""),
          lastErrorHint: "",
          lastSpeaker: String(s.lastSpeaker || latestRunSummary.speaker || "assistant"),
          lastSenderType: String(s.lastSenderType || latestRunSummary.sender_type || "legacy"),
          lastSenderName: String(s.lastSenderName || latestRunSummary.sender_name || ""),
          lastSenderSource: String(s.lastSenderSource || latestRunSummary.sender_source || "legacy"),
          runCount: Math.max(0, Number(s.runCount || latestRunSummary.run_count || 0) || 0),
          latestUserMsg: String(s.latestUserMsg || latestRunSummary.latest_user_msg || ""),
          latestAiMsg: String(s.latestAiMsg || latestRunSummary.latest_ai_msg || ""),
          session_display_state: sessionDisplayState,
          session_display_reason: String(firstNonEmptyText([s.session_display_reason, s.sessionDisplayReason]) || ""),
          latest_run_summary: latestRunSummary,
          runtime_state: runtimeState,
          heartbeat_summary: heartbeatSummary,
        };
      });
    }

    async function fetchConversationSessionsFromApi(projectId, channelName) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return [];
      const qs = new URLSearchParams();
      qs.set("project_id", pid);
      if (channelName) qs.set("channel_name", String(channelName));
      const r = await fetch("/api/sessions?" + qs.toString(), { cache: "no-store" });
      if (!r.ok) {
        throw new Error("loadChannelSessions failed: " + String(r.status || "unknown"));
      }
      const j = await r.json();
      const sessions = Array.isArray(j && j.sessions) ? j.sessions : [];
      return formatConversationSessionsFromApi(pid, sessions);
    }

    async function ensureConversationProjectSessionDirectory(projectId, opts = {}) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return [];
      ensureConversationSessionDirectoryStateMaps();
      const force = !!(opts && opts.force);
      const existing = Array.isArray(PCONV.sessionDirectoryByProject[pid])
        ? PCONV.sessionDirectoryByProject[pid].slice()
        : [];
      const meta = PCONV.sessionDirectoryMetaByProject[pid] || null;
      if (!force && meta && meta.liveLoaded && Array.isArray(PCONV.sessionDirectoryByProject[pid])) {
        return existing;
      }
      if (!force && PCONV.sessionDirectoryPromiseByProject[pid]) {
        return PCONV.sessionDirectoryPromiseByProject[pid];
      }
      const task = (async () => {
        try {
          const serverSessions = await fetchConversationSessionsFromApi(pid, "");
          const merged = mergeConversationSessions(configuredProjectConversations(pid), serverSessions);
          PCONV.sessionDirectoryByProject[pid] = merged.slice();
          markConversationSessionDirectoryMeta(pid, {
            liveLoaded: true,
            source: "api",
            loadedAt: new Date().toISOString(),
            error: "",
          });
          return merged.slice();
        } catch (err) {
          const fallback = existing.length ? existing : mergeConversationSessions(configuredProjectConversations(pid), []);
          if (!existing.length) PCONV.sessionDirectoryByProject[pid] = fallback.slice();
          markConversationSessionDirectoryMeta(pid, {
            liveLoaded: false,
            source: existing.length ? "cache" : "config",
            loadedAt: new Date().toISOString(),
            error: String((err && err.message) || err || "unknown"),
          });
          return fallback.slice();
        } finally {
          delete PCONV.sessionDirectoryPromiseByProject[pid];
        }
      })();
      PCONV.sessionDirectoryPromiseByProject[pid] = task;
      return task;
    }

    async function createNewConversation() {
      const projSelect = document.getElementById("newConvProject");
      const chSelect = document.getElementById("newConvChannel");
      const cliSelect = document.getElementById("newConvCliType");
      const createBtn = document.getElementById("newConvCreateBtn");
      const sidInput = document.getElementById("newConvSessionId");
      const modelInput = document.getElementById("newConvModel");
      const purposeInput = document.getElementById("newConvPurpose");
      const aliasInput = document.getElementById("newConvAlias");
      const sessionRoleInput = document.getElementById("newConvSessionRole");
      const reuseStrategyInput = document.getElementById("newConvReuseStrategy");
      const environmentInput = document.getElementById("newConvEnvironment");
      const worktreeRootInput = document.getElementById("newConvWorktreeRoot");
      const workdirInput = document.getElementById("newConvWorkdir");
      const branchInput = document.getElementById("newConvBranch");
      const initMessageInput = document.getElementById("newConvInitMessage");

      const pid = String((projSelect && projSelect.value) || "");
      const ch = String((chSelect && chSelect.value) || "");
      const cli = String((cliSelect && cliSelect.value) || "codex");
      const mode = normalizeNewConvMode(NEW_CONV_UI.mode);
      const sidFromInput = String((sidInput && sidInput.value) || "").trim();
      const model = normalizeSessionModel(modelInput && modelInput.value);
      const purpose = String((purposeInput && purposeInput.value) || "").trim();
      const alias = String((aliasInput && aliasInput.value) || "").trim();
      const sessionRole = String((sessionRoleInput && sessionRoleInput.value) || "child").trim() || "child";
      const reuseStrategy = String((reuseStrategyInput && reuseStrategyInput.value) || "create_new").trim() || "create_new";
      const environment = normalizeSessionEnvironmentValue((environmentInput && environmentInput.value) || "stable");
      const worktreeRoot = String((worktreeRootInput && worktreeRootInput.value) || "").trim();
      const workdir = String((workdirInput && workdirInput.value) || "").trim();
      const branch = String((branchInput && branchInput.value) || "").trim();
      const initMessage = String((initMessageInput && initMessageInput.value) || "").trim();

      if (!pid || pid === "overview") {
        newConvModalError("请选择项目");
        return;
      }
      if (!ch) {
        newConvModalError("请选择通道");
        return;
      }

      const oldText = createBtn ? createBtn.textContent : "";
      if (createBtn) {
        createBtn.disabled = true;
        createBtn.textContent = mode === "attach" ? "绑定中..." : "创建中...";
      }
      newConvModalError("");

      try {
        let sid = "";
        let effectiveCli = cli;
        let tip = "";
        let timeoutRecovered = false;
        const appendContextHint = (baseTip, payload) => {
          const meta = buildProjectExecutionContextMeta(
            payload && (payload.project_execution_context || payload.projectExecutionContext || null)
          );
          if (!meta.available) return String(baseTip || "");
          return String(baseTip || "") + " 上下文来源：" + String((meta.sourceMeta && meta.sourceMeta.text) || "待返回") + "。";
        };

        if (mode === "attach") {
          if (!looksLikeSessionId(sidFromInput)) {
            newConvModalError("Session ID 格式不正确（支持 UUID 或 ses_...）。");
            return;
          }
          const r = await fetch("/api/sessions", {
            method: "POST",
            headers: authHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify({
              project_id: pid,
              channel_name: ch,
              mode: "attach_existing",
              session_id: sidFromInput,
              cli_type: cli,
              model,
              alias,
              purpose,
              session_role: sessionRole,
              reuse_strategy: "attach_existing",
              set_as_primary: sessionRole === "primary",
              environment,
              worktree_root: worktreeRoot,
              workdir,
              branch,
            }),
          });
          const j = await r.json().catch(() => ({}));
          if (!r.ok) {
            const detail = j && (j.error || j.message || (j.detail && (j.detail.error || j.detail.message)));
            newConvModalError("补登记失败：" + String(detail || "unknown"));
            return;
          }
          const session = j && j.session;
          sid = String((session && session.id) || sidFromInput || "").trim();
          if (!sid) {
            newConvModalError("补登记失败：未获取到 session_id");
            return;
          }
          if (session && session.cli_type) effectiveCli = String(session.cli_type);
          const ok = await setBinding(pid, ch, sid, effectiveCli);
          if (!ok) {
            newConvModalError("补登记成功但绑定失败：未能写入服务端会话绑定（请检查 Token 或服务状态）。");
            return;
          }
          const probe = await fetch("/api/sessions/" + encodeURIComponent(sid), { cache: "no-store" }).catch(() => null);
          if (!probe || !probe.ok) {
            tip = "已补登记并绑定已有对话，但当前详情读取失败，请刷新后重试。";
          } else {
            const probePayload = await probe.json().catch(() => ({}));
            tip = (j && j.imported)
              ? "已补登记并绑定已有对话，可直接发送消息。"
              : "已恢复并绑定已有对话，可直接发送消息。";
            if (model) {
              const modelUpdated = await tryUpdateSessionModel(sid, model);
              if (modelUpdated) tip = "已绑定已有对话，并更新模型配置。";
            }
            tip = appendContextHint(tip, probePayload);
          }
        } else {
          // 调用新的 POST /api/sessions API 创建会话
          const r = await fetch("/api/sessions", {
            method: "POST",
            headers: authHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify({
              project_id: pid,
              channel_name: ch,
              cli_type: cli,
              model,
              alias,
              purpose,
              session_role: sessionRole,
              reuse_strategy: reuseStrategy,
              set_as_primary: sessionRole === "primary",
              environment,
              worktree_root: worktreeRoot,
              workdir,
              branch,
            }),
          });
          const j = await r.json().catch(() => ({}));
          if (!r.ok) {
            const detailObj = (j && typeof j.detail === "object") ? j.detail : null;
            const timeoutErr = String(
              (detailObj && detailObj.error)
              || (j && j.error)
              || ""
            ).toLowerCase();
            const timeoutSid = String(
              (detailObj && (detailObj.sessionId || detailObj.session_id))
              || ""
            ).trim();
            if (timeoutSid && looksLikeSessionId(timeoutSid) && timeoutErr.indexOf("timeout") >= 0) {
              sid = timeoutSid;
              timeoutRecovered = true;
            }
            const detail = j && (j.detail || j.error || j.message);
            let detailStr;
            if (detail && typeof detail === "object") {
              detailStr = detail.error || detail.message || JSON.stringify(detail);
            } else {
              detailStr = String(detail || "unknown");
            }
            if (!sid) {
              newConvModalError("创建失败：" + detailStr);
              return;
            }
          }
          const session = j && j.session;
          if (!sid) sid = session && session.id ? String(session.id).trim() : "";
          if (!sid) {
            newConvModalError("创建失败：未获取到 session_id");
            return;
          }
          if (session && session.cli_type) effectiveCli = String(session.cli_type);
          const ok = await setBinding(pid, ch, sid, effectiveCli);
          if (!ok) {
            newConvModalError("创建成功但绑定失败：请检查 Token 或服务状态后重试绑定。");
            return;
          }
          tip = timeoutRecovered
            ? "已完成 timeout-recovered 绑定。"
            : (j && j.reused ? "已复用并绑定现有对话。" : "已创建并绑定新对话。");
          if (initMessage) {
            if (createBtn) createBtn.textContent = "首发中...";
            const bootstrapMode = /^\s*--bootstrap-message\s*$/i.test(initMessage);
            if (bootstrapMode) {
              const msgs = buildBootstrapVisibleMessages(ch);
              const sendA = await sendNewConversationInitMessage(pid, ch, sid, effectiveCli, msgs[0], model);
              const sendB = sendA.ok
                ? await sendNewConversationInitMessage(pid, ch, sid, effectiveCli, msgs[1], model)
                : { ok: false };
              if (sendA.ok && sendB.ok) {
                tip = (timeoutRecovered ? "已完成 timeout-recovered 绑定，" : "已创建并绑定新对话，") + "并自动发送两条标准首发消息。";
              } else {
                tip = (timeoutRecovered ? "已完成 timeout-recovered 绑定，" : "已创建并绑定新对话，") + "但标准首发消息发送不完整，请手动补发。";
              }
            } else {
              const sendRet = await sendNewConversationInitMessage(pid, ch, sid, effectiveCli, initMessage, model);
              if (sendRet.ok) {
                tip = (timeoutRecovered ? "已完成 timeout-recovered 绑定，" : "已创建并绑定新对话，") + "并自动发送初始化消息。";
              } else {
                tip = (timeoutRecovered ? "已完成 timeout-recovered 绑定，" : "已创建并绑定新对话，") + "但初始化消息发送失败，请手动发送。";
              }
            }
          }
          tip = appendContextHint(tip, session || j || null);
        }

        const visRet = await verifySessionBindingVisibility(pid, ch, sid);
        if (visRet.ok && visRet.hardRefreshRequired) {
          tip += " 已自动重建看板；请按 Cmd+Shift+R 强刷后确认可见性。";
        }

        closeNewConvModal();
        await refreshConversationPanel();
        setSelectedSessionId(sid, true, { explicit: true });
        setHintText(STATE.panelMode, tip);
        render();
      } catch (err) {
        newConvModalError((mode === "attach" ? "绑定失败：" : "创建失败：") + "网络或服务异常");
      } finally {
        if (createBtn) {
          createBtn.disabled = false;
          createBtn.textContent = oldText || (mode === "attach" ? "绑定已有对话" : "创建并绑定");
        }
      }
    }

    // 加载指定通道的会话列表
    async function loadChannelSessions(projectId, channelName) {
      if (!projectId || projectId === "overview") {
        PCONV.sessions = [];
        return;
      }
      try {
        const formatted = await fetchConversationSessionsFromApi(projectId, channelName);
        // 更新 PCONV.sessions
        if (channelName) {
          // 只更新当前通道的会话，保留其他通道的会话
          const otherSessions = PCONV.sessions.filter(s => s.channel_name !== channelName);
          PCONV.sessions = [...otherSessions, ...formatted];
        } else {
          PCONV.sessions = formatted;
          ensureConversationSessionDirectoryStateMaps();
          PCONV.sessionDirectoryByProject[String(projectId)] = mergeConversationSessions(configuredProjectConversations(projectId), formatted);
          markConversationSessionDirectoryMeta(projectId, {
            liveLoaded: true,
            source: "api",
            loadedAt: new Date().toISOString(),
            error: "",
          });
        }
        PCONV.lastRefreshAt = new Date().toLocaleTimeString("zh-CN", { hour12: false });
      } catch (err) {
        console.error("loadChannelSessions error:", err);
      }
    }

    function normalizeConversationSession(raw) {
      if (!raw) return null;
      const sid = String(raw.sessionId || raw.id || raw.session_id || "").trim();
      if (!looksLikeSessionId(sid)) return null;
      const channelName = String(
        raw.channel_name || raw.primaryChannel || raw.name ||
        (Array.isArray(raw.channels) && raw.channels.length ? raw.channels[0] : "")
      ).trim();
      const presentation = resolveConversationSessionPresentation(raw, channelName, sid);
      const channels = Array.isArray(raw.channels)
        ? raw.channels.map(x => String(x || "").trim()).filter(Boolean)
        : [];
      if (channelName && !channels.includes(channelName)) channels.unshift(channelName);
      const rawHeartbeat = (raw.heartbeat && typeof raw.heartbeat === "object") ? raw.heartbeat : {};
      const heartbeatItems = Array.isArray(rawHeartbeat.items)
        ? normalizeHeartbeatTaskItemsClient(rawHeartbeat.items, String(STATE.project || "").trim(), rawHeartbeat)
        : [];
      const heartbeatSummary = normalizeHeartbeatSummaryClient(
        raw.heartbeat_summary || raw.heartbeatSummary || rawHeartbeat.summary || {},
        heartbeatItems
      );

      return {
        sessionId: sid,
        id: sid,
        channel_name: channelName,
        primaryChannel: channelName || "",
        channels,
        alias: presentation.alias,
        displayChannel: presentation.displayChannel,
        displayName: presentation.displayName,
        displayNameSource: presentation.displayNameSource,
        codexTitle: String(raw.codexTitle || raw.codex_title || ""),
        environment: normalizeSessionEnvironmentValue(raw.environment || raw.environmentName || "stable"),
        worktree_root: String(raw.worktree_root || raw.worktreeRoot || ""),
        workdir: String(raw.workdir || ""),
        branch: String(raw.branch || ""),
        cli_type: String(raw.cli_type || raw.cliType || "codex"),
        model: normalizeSessionModel(raw.model),
        reasoning_effort: normalizeReasoningEffort(raw.reasoning_effort || raw.reasoningEffort),
        status: String(raw.status || "active"),
        created_at: String(raw.created_at || ""),
        last_used_at: String(raw.last_used_at || ""),
        is_primary: boolLike(raw.is_primary || raw.isPrimary),
        is_deleted: boolLike(raw.is_deleted || raw.isDeleted),
        deleted_at: String(raw.deleted_at || raw.deletedAt || ""),
        deleted_reason: String(raw.deleted_reason || raw.deletedReason || ""),
        source: String(raw.source || ""),
        context_binding_state: String(raw.context_binding_state || raw.contextBindingState || ""),
        lastActiveAt: String(raw.lastActiveAt || raw.last_used_at || ""),
        lastStatus: normalizeDisplayState(
          firstNonEmptyText([raw.session_display_state, raw.sessionDisplayState, raw.lastStatus]) || "idle",
          "idle"
        ),
        lastPreview: String(raw.lastPreview || normalizeLatestRunSummary(raw.latest_run_summary || raw.latestRunSummary || null).preview || ""),
        lastTimeout: boolLike(raw.lastTimeout || raw.last_timeout),
        lastError: String(raw.lastError || raw.last_error || ""),
        lastErrorHint: String(raw.lastErrorHint || raw.last_error_hint || ""),
        lastSpeaker: String(raw.lastSpeaker || "assistant"),
        lastSenderType: String(raw.lastSenderType || "legacy"),
        lastSenderName: String(raw.lastSenderName || ""),
        lastSenderSource: String(raw.lastSenderSource || "legacy"),
        runCount: Number(raw.runCount || 0),
        latestUserMsg: String(raw.latestUserMsg || ""),
        latestAiMsg: String(raw.latestAiMsg || ""),
        session_display_state: normalizeDisplayState(
          firstNonEmptyText([
            raw.session_display_state,
            raw.sessionDisplayState,
            raw.runtime_state && raw.runtime_state.display_state,
            raw.runtimeState && raw.runtimeState.display_state,
          ]) || "idle",
          "idle"
        ),
        session_display_reason: String(firstNonEmptyText([raw.session_display_reason, raw.sessionDisplayReason]) || ""),
        latest_run_summary: normalizeLatestRunSummary(raw.latest_run_summary || raw.latestRunSummary || null),
        runtime_state: normalizeRuntimeState(raw.runtime_state || raw.runtimeState || null),
        heartbeat_summary: heartbeatSummary,
        project_execution_context: normalizeProjectExecutionContext(
          raw.project_execution_context || raw.projectExecutionContext || null
        ),
      };
    }

    function mergeConversationSessions(localSessions, serverSessions) {
      const map = new Map();
      const serverChannelSessions = new Map();

      for (const raw of (Array.isArray(serverSessions) ? serverSessions : [])) {
        const n = normalizeConversationSession(raw);
        if (!n) continue;
        const channelKey = String(n.channel_name || n.primaryChannel || "").trim();
        if (channelKey) {
          let bucket = serverChannelSessions.get(channelKey);
          if (!bucket) {
            bucket = new Set();
            serverChannelSessions.set(channelKey, bucket);
          }
          bucket.add(n.sessionId);
        }
      }

      for (const raw of (Array.isArray(localSessions) ? localSessions : [])) {
        const n = normalizeConversationSession(raw);
        if (!n) continue;
        const channelKey = String(n.channel_name || n.primaryChannel || "").trim();
        const channelBucket = channelKey ? serverChannelSessions.get(channelKey) : null;
        if (channelBucket && channelBucket.size && !channelBucket.has(n.sessionId)) continue;
        map.set(n.sessionId, n);
      }
      for (const raw of (Array.isArray(serverSessions) ? serverSessions : [])) {
        const n = normalizeConversationSession(raw);
        if (!n) continue;
        const prev = map.get(n.sessionId);
        if (!prev) {
          map.set(n.sessionId, n);
          continue;
        }
        const channels = Array.from(new Set([...(prev.channels || []), ...(n.channels || [])].filter(Boolean)));
        const nextRuntime = normalizeRuntimeState(n.runtime_state || n.runtimeState || null);
        const nextExecContext = buildProjectExecutionContextMeta(n.project_execution_context || null);
        const prevExecContext = buildProjectExecutionContextMeta(prev.project_execution_context || null);
        const nextDisplayState = normalizeDisplayState(
          firstNonEmptyText([n.session_display_state, n.sessionDisplayState, nextRuntime.display_state]) || "idle",
          "idle"
        );
        const mergedAlias = String(n.alias || prev.alias || "").trim();
        const mergedChannelName = String(n.channel_name || prev.channel_name || "").trim();
        const mergedPresentation = resolveConversationSessionPresentation({
          alias: mergedAlias,
          displayChannel: n.displayChannel || prev.displayChannel || "",
          displayName: n.displayName || prev.displayName || "",
          display_name_source: n.displayNameSource || prev.displayNameSource || "",
        }, mergedChannelName, n.sessionId);
        map.set(n.sessionId, {
          ...prev,
          ...n,
          channels,
          channel_name: n.channel_name || prev.channel_name,
          primaryChannel: n.primaryChannel || prev.primaryChannel,
          displayChannel: mergedPresentation.displayChannel,
          displayName: mergedPresentation.displayName,
          displayNameSource: mergedPresentation.displayNameSource,
          codexTitle: n.codexTitle || prev.codexTitle,
          alias: mergedAlias,
          cli_type: n.cli_type || prev.cli_type,
          model: normalizeSessionModel(n.model || prev.model),
          reasoning_effort: normalizeReasoningEffort(n.reasoning_effort || prev.reasoning_effort),
          // Prefer server-provided primary flag when present, avoid stale local cache elevating old sessions to primary.
          is_primary: String(n.source || "").trim()
            ? boolLike(n.is_primary)
            : (boolLike(n.is_primary) || boolLike(prev.is_primary)),
          is_deleted: boolLike(n.is_deleted || prev.is_deleted),
          deleted_at: firstNonEmptyText([n.deleted_at, prev.deleted_at]),
          deleted_reason: firstNonEmptyText([n.deleted_reason, prev.deleted_reason]),
          source: firstNonEmptyText([n.source, prev.source]),
          runtime_state: nextRuntime,
          session_display_state: nextDisplayState,
          session_display_reason: firstNonEmptyText([n.session_display_reason, prev.session_display_reason]),
          latest_run_summary: n.latest_run_summary || prev.latest_run_summary || normalizeLatestRunSummary(null),
          lastStatus: nextDisplayState,
          lastPreview: String(n.lastPreview || prev.lastPreview || ""),
          lastError: String(n.lastError || prev.lastError || ""),
          lastSpeaker: String(n.lastSpeaker || prev.lastSpeaker || "assistant"),
          lastSenderType: String(n.lastSenderType || prev.lastSenderType || "legacy"),
          lastSenderName: String(n.lastSenderName || prev.lastSenderName || ""),
          lastSenderSource: String(n.lastSenderSource || prev.lastSenderSource || "legacy"),
          latestUserMsg: String(n.latestUserMsg || prev.latestUserMsg || ""),
          latestAiMsg: String(n.latestAiMsg || prev.latestAiMsg || ""),
          runCount: Math.max(0, Number(n.runCount || prev.runCount || 0) || 0),
          lastActiveAt: String(n.lastActiveAt || prev.lastActiveAt || n.last_used_at || prev.last_used_at || ""),
          heartbeat_summary: normalizeHeartbeatSummaryClient(
            n.heartbeat_summary || prev.heartbeat_summary || {},
            []
          ),
          project_execution_context: nextExecContext.available
            ? n.project_execution_context
            : (prevExecContext.available ? prev.project_execution_context : n.project_execution_context),
        });
      }

      return Array.from(map.values());
    }

    const NEW_CHANNEL_UI = {
      open: false,
      submitting: false,
      inputBound: false,
      phase: "form",
      mode: "direct",
      selectedAgentSessionId: "",
      selectedAgent: null,
      agentCandidates: [],
      agentCandidatesProjectId: "",
      agentLoading: false,
      agentError: "",
      agentMenuOpen: false,
    };
