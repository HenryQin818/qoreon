    function renderConvComposerMentionsByKey(key) {
      const { mentionContainer } = convComposerUiElements();
      const draftKey = String(key || "").trim();
      if (!mentionContainer) return;
      mentionContainer.innerHTML = "";
      const draft = getConvComposerDraftByKey(key);
      const mentions = Array.isArray(draft.mentions) ? draft.mentions : [];
      if (!mentions.length) {
        mentionContainer.style.display = "none";
        renderConversationRecentAgentsByKey(draftKey);
        return;
      }
      mentionContainer.style.display = "flex";
      const lead = el("span", {
        class: "mention-count",
        text: "协同对象 " + mentions.length,
      });
      mentionContainer.appendChild(lead);
      mentions.forEach((m) => {
        const tag = el("span", {
          class: "mention-tag",
          title: (String((m && m.project_name) || "").trim() ? ("项目: " + String((m && m.project_name) || "") + "\n") : "")
            + String((m && m.channel_name) || "") + "\nsession_id: " + String((m && m.session_id) || ""),
        });
        tag.appendChild(el("span", { class: "mention-tag-label", text: mentionInsertLabel(m) || String((m && m.display_name) || (m && m.channel_name) || "协同对象") }));
        const removeBtn = el("button", { class: "mention-tag-remove", type: "button", text: "×", title: "移除协同对象" });
        removeBtn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          removeConvComposerMentionByKey(draftKey, m);
        });
        tag.appendChild(removeBtn);
        mentionContainer.appendChild(tag);
      });
      renderConversationRecentAgentsByKey(draftKey);
    }

    function currentProjectMentionSuggestMode() {
      return "project";
    }

    function globalProjectMentionSuggestMode() {
      return "global";
    }

    function emptyConvMentionSuggestState() {
      return {
        open: false,
        mode: currentProjectMentionSuggestMode(),
        query: "",
        activeIndex: 0,
        anchorStart: -1,
        anchorEnd: -1,
        candidates: [],
        groups: [],
        draftKey: "",
      };
    }

    function mentionProjectLabel(projectId, fallbackName = "") {
      const pid = String(projectId || "").trim();
      const project = pid ? projectById(pid) : null;
      const display = String(project ? displayProjectName(project) : "").trim();
      if (display) return display;
      return String(fallbackName || pid || "").trim();
    }

    function mentionBaseLabel(raw) {
      const m = normalizeMentionTargetItem(raw);
      if (!m) return "";
      const display = String(m.display_name || "").trim();
      const channel = String(m.channel_name || "").trim();
      if (display && !/\s/.test(display)) return display;
      if (channel && !/\s/.test(channel)) return channel;
      const fallback = display || channel || "协同对象";
      return fallback.replace(/\s+/g, "");
    }

    function sanitizeMentionLabelSegment(raw) {
      return String(raw || "").trim().replace(/[^\u4e00-\u9fa5A-Za-z0-9._-]+/g, "");
    }

    function globalMentionScopedLabel(raw) {
      const m = normalizeMentionTargetItem(raw);
      if (!m) return "";
      const projectPart = sanitizeMentionLabelSegment(firstNonEmptyText([
        m.project_id,
        m.project_name,
      ]));
      const agentPart = sanitizeMentionLabelSegment(mentionBaseLabel(m));
      if (projectPart && agentPart) return projectPart + "/" + agentPart;
      return agentPart || projectPart || "协同对象";
    }

    function conversationMentionSessionsForProject(projectId) {
      const pid = String(projectId || STATE.project || "").trim();
      if (!pid || pid === "overview") return [];
      const local = PCONV.sessionDirectoryByProject && PCONV.sessionDirectoryByProject[pid];
      if (Array.isArray(local) && local.length) {
        return local.filter((session) => !(typeof isDeletedSession === "function" && isDeletedSession(session)));
      }
      return conversationSessionsForProject(pid);
    }

    function isConversationRecentAgentTargetDeleted(raw, projectId = "") {
      const target = normalizeMentionTargetItem(raw);
      if (!target) return false;
      const sessionId = String(target.session_id || "").trim();
      if (!sessionId) return false;
      const pid = String(target.project_id || projectId || STATE.project || "").trim();
      const source = (PCONV.sessionDirectoryByProject && Array.isArray(PCONV.sessionDirectoryByProject[pid]))
        ? PCONV.sessionDirectoryByProject[pid]
        : [];
      if (!source.length) return false;
      const hit = source.find((session) => String(getSessionId(session) || "").trim() === sessionId);
      if (!hit) return false;
      return typeof isDeletedSession === "function" ? isDeletedSession(hit) : false;
    }

    function filterConversationRecentAgentItems(items, projectId = "") {
      return (Array.isArray(items) ? items : []).filter((item) => {
        if (!item || typeof item !== "object") return false;
        const session = (item.session && typeof item.session === "object") ? item.session : null;
        if (session) {
          return !(typeof isDeletedSession === "function" && isDeletedSession(session));
        }
        return !isConversationRecentAgentTargetDeleted(item.target, projectId);
      });
    }

    function mentionTargetFromConversationSession(session, projectId, opts = {}) {
      const pid = String(projectId || "").trim();
      const target = normalizeMentionTargetItem({
        channel_name: getSessionChannelName(session),
        session_id: getSessionId(session),
        cli_type: firstNonEmptyText([session && session.cli_type, "codex"]),
        display_name: conversationDisplayName(session),
        project_id: pid,
        project_name: mentionProjectLabel(pid),
      });
      if (!target) return null;
      if (opts.scopeMode === globalProjectMentionSuggestMode()) {
        target.mention_label = globalMentionScopedLabel(target);
      }
      return target;
    }

    function getConvComposerMentionsForCurrentSession() {
      const key = currentConvComposerDraftKey();
      if (!key) return [];
      const d = ensureConvComposerDraftByKey(key);
      return Array.isArray(d.mentions) ? d.mentions : [];
    }

    function appendConvComposerMentionByKey(key, mentionTarget) {
      const normalized = normalizeMentionTargetItem(mentionTarget);
      if (!normalized) return false;
      const k = mentionTargetKey(normalized);
      if (!k) return false;
      let added = false;
      updateConvComposerDraftByKey(key, (d) => {
        d.mentions = cloneConvComposerMentionTargets(d.mentions);
        const exists = d.mentions.some((x) => mentionTargetKey(x) === k);
        if (!exists) {
          d.mentions.push(normalized);
          added = true;
        }
      });
      if (String(PCONV.composerBoundDraftKey || "") === String(key || "")) renderAttachments();
      return added;
    }

    function removeConvComposerMentionByKey(key, mentionTarget) {
      const k = mentionTargetKey(mentionTarget);
      if (!k) return;
      const draftKey = String(key || "").trim();
      if (!draftKey) return;
      const draft = getConvComposerDraftByKey(draftKey);
      const nextText = removeMentionTokensFromText(draft.text, mentionTarget);
      syncConvComposerMentionsByKeyFromText(draftKey, nextText);
      if (String(PCONV.composerBoundDraftKey || "") === draftKey) {
        const { input } = convComposerUiElements();
        if (input) {
          input.value = nextText;
          try {
            const pos = input.value.length;
            input.setSelectionRange(pos, pos);
          } catch (_) {}
          if (typeof input.__adjustHeight === "function") input.__adjustHeight();
          else setMessageInputHeight(input);
          try { input.focus(); } catch (_) {}
        }
        renderAttachments();
      }
      renderConvComposerMentionsByKey(draftKey);
    }

    function conversationMentionDirectory(projectId) {
      const pid = String(projectId || STATE.project || "").trim();
      if (!pid || pid === "overview") return [];
      const sessions = conversationMentionSessionsForProject(pid);
      const out = [];
      const seen = new Set();
      sessions.forEach((s) => {
        const target = mentionTargetFromConversationSession(s, pid);
        if (!target) return;
        const key = mentionTargetKey(target);
        if (!key || seen.has(key)) return;
        seen.add(key);
        out.push(target);
      });
      out.sort((a, b) => String(a.display_name || "").localeCompare(String(b.display_name || ""), "zh-Hans-CN"));
      return out;
    }

    function conversationGlobalMentionDirectory(projectId) {
      const currentPid = String(projectId || STATE.project || "").trim();
      const projects = Array.isArray(DATA.projects) ? DATA.projects.slice() : [];
      const ordered = projects.slice().sort((a, b) => {
        const pidA = String((a && a.id) || "").trim();
        const pidB = String((b && b.id) || "").trim();
        if (pidA === currentPid && pidB !== currentPid) return -1;
        if (pidB === currentPid && pidA !== currentPid) return 1;
        return mentionProjectLabel(pidA).localeCompare(mentionProjectLabel(pidB), "zh-Hans-CN");
      });
      const out = [];
      const seen = new Set();
      ordered.forEach((project) => {
        const pid = String((project && project.id) || "").trim();
        if (!pid) return;
        conversationMentionSessionsForProject(pid).forEach((session) => {
          const target = mentionTargetFromConversationSession(session, pid, {
            scopeMode: globalProjectMentionSuggestMode(),
          });
          if (!target) return;
          const key = mentionTargetKey(target);
          if (!key || seen.has(key)) return;
          seen.add(key);
          out.push(target);
        });
      });
      out.sort((a, b) => {
        const pidA = String(a && a.project_id || "").trim();
        const pidB = String(b && b.project_id || "").trim();
        if (pidA === currentPid && pidB !== currentPid) return -1;
        if (pidB === currentPid && pidA !== currentPid) return 1;
        const byProject = mentionProjectLabel(pidA, a && a.project_name).localeCompare(
          mentionProjectLabel(pidB, b && b.project_name),
          "zh-Hans-CN"
        );
        if (byProject !== 0) return byProject;
        return String(a && a.display_name || "").localeCompare(String(b && b.display_name || ""), "zh-Hans-CN");
      });
      return out;
    }

    function hydrateConversationGlobalMentionDirectory(projectId) {
      const currentPid = String(projectId || STATE.project || "").trim();
      const projects = Array.isArray(DATA.projects) ? DATA.projects : [];
      projects.forEach((project) => {
        const pid = String((project && project.id) || "").trim();
        if (!pid || pid === "overview") return;
        ensureConversationSessionDirectoryStateMaps();
        const meta = PCONV.sessionDirectoryMetaByProject[pid] || null;
        if (meta && meta.liveLoaded) return;
        if (PCONV.sessionDirectoryPromiseByProject[pid]) return;
        ensureConversationProjectSessionDirectory(pid).then(() => {
          const st = PCONV.mentionSuggest || {};
          if (!st.open) return;
          if (String(st.mode || "") !== globalProjectMentionSuggestMode()) return;
          if (String(STATE.project || "") !== currentPid) return;
          updateConvMentionSuggestByInput();
        }).catch(() => {});
      });
    }

    function mentionInsertLabel(raw) {
      const m = normalizeMentionTargetItem(raw);
      if (!m) return "";
      const explicit = String(m.mention_label || "").trim();
      if (explicit) return explicit;
      return mentionBaseLabel(m);
    }

    function normalizeConversationRecentAgentLookupKey(raw) {
      return String(raw || "").trim().toLowerCase().replace(/\s+/g, "");
    }

    function cloneConversationRecentAgentTarget(raw, currentProjectId = "") {
      const target = normalizeMentionTargetItem(raw);
      if (!target) return null;
      const projectId = String(currentProjectId || "").trim();
      if (!target.project_id && projectId) target.project_id = projectId;
      if (!target.mention_label && target.project_id && projectId && target.project_id !== projectId) {
        target.mention_label = globalMentionScopedLabel(target);
      }
      return target;
    }

    function registerConversationRecentAgentLookup(index, session, rawName) {
      if (!index || !session) return;
      const lookupKey = normalizeConversationRecentAgentLookupKey(rawName);
      if (!lookupKey || index.byLookup.has(lookupKey)) return;
      index.byLookup.set(lookupKey, session);
    }

    function conversationRecentAgentSessionProjectId(session, currentProjectId = "") {
      return String(firstNonEmptyText([
        session && session.project_id,
        session && session.projectId,
        currentProjectId,
        STATE.project,
      ]) || "").trim();
    }

    function conversationRecentAgentTargetFromSession(session, currentProjectId = "") {
      const sessionProjectId = conversationRecentAgentSessionProjectId(session, currentProjectId);
      if (!sessionProjectId) return null;
      return mentionTargetFromConversationSession(session, sessionProjectId, {
        scopeMode: sessionProjectId && currentProjectId && sessionProjectId !== currentProjectId
          ? globalProjectMentionSuggestMode()
          : currentProjectMentionSuggestMode(),
      });
    }

    function buildConversationRecentAgentDirectoryIndex(projectId) {
      const currentProjectId = String(projectId || STATE.project || "").trim();
      const index = {
        bySessionId: new Map(),
        byLookup: new Map(),
      };
      const registerSession = (session) => {
        if (!session || (typeof isDeletedSession === "function" && isDeletedSession(session))) return;
        const sid = String(getSessionId(session) || "").trim().toLowerCase();
        if (!sid) return;
        if (!index.bySessionId.has(sid)) index.bySessionId.set(sid, session);
        const target = conversationRecentAgentTargetFromSession(session, currentProjectId);
        const sessionProjectId = conversationRecentAgentSessionProjectId(session, currentProjectId);
        [
          conversationAgentName(session),
          session && session.alias,
          session && session.displayName,
          session && session.display_name,
          session && session.codexTitle,
          session && session.displayChannel,
          getSessionChannelName(session),
          session && session.primaryChannel,
          target && mentionInsertLabel(target),
          target && target.display_name,
          target && target.channel_name,
          sessionProjectId ? (sessionProjectId + "/" + String(conversationAgentName(session) || "")) : "",
          sessionProjectId ? (sessionProjectId + "/" + String(getSessionChannelName(session) || "")) : "",
        ].forEach((name) => registerConversationRecentAgentLookup(index, session, name));
      };
      conversationMentionSessionsForProject(currentProjectId).forEach(registerSession);
      (Array.isArray(DATA.projects) ? DATA.projects : []).forEach((project) => {
        const pid = String((project && project.id) || "").trim();
        if (!pid || pid === currentProjectId) return;
        conversationMentionSessionsForProject(pid).forEach(registerSession);
      });
      return index;
    }

    function parseConversationRecentAgentRef(raw) {
      if (!raw) return null;
      if (typeof raw === "object" && !Array.isArray(raw)) return raw;
      const text = String(raw || "").trim();
      if (!text) return null;
      const sessionId = String(((text.match(/(?:^|[·\s])session=([^\s·]+)/) || [])[1] || "")).trim();
      const channelName = String(((text.match(/channel=([^·]+?)(?:\s*·|$)/) || [])[1] || "")).trim();
      if (!sessionId && !channelName) return null;
      return {
        session_id: sessionId,
        channel_name: channelName,
      };
    }

    function resolveConversationRecentAgentSession(raw, projectId, index) {
      const ref = parseConversationRecentAgentRef(raw) || raw;
      const sessionId = String(firstNonEmptyText([
        ref && ref.session_id,
        ref && ref.sessionId,
        ref && ref.sender_id,
        ref && ref.senderId,
        ref && ref.id,
      ]) || "").trim();
      if (sessionId && index && index.bySessionId.has(sessionId.toLowerCase())) {
        return index.bySessionId.get(sessionId.toLowerCase()) || null;
      }
      const names = [
        ref && ref.display_name,
        ref && ref.displayName,
        ref && ref.sender_name,
        ref && ref.senderName,
        ref && ref.channel_name,
        ref && ref.channelName,
        ref && ref.channel,
        ref && ref.label,
        ref && ref.alias,
        ref && ref.name,
      ];
      for (const one of names) {
        const lookupKey = normalizeConversationRecentAgentLookupKey(one);
        if (!lookupKey || !index || !index.byLookup.has(lookupKey)) continue;
        return index.byLookup.get(lookupKey) || null;
      }
      return null;
    }

    function resolveConversationRecentAgentTarget(raw, projectId, index) {
      const currentProjectId = String(projectId || STATE.project || "").trim();
      const session = resolveConversationRecentAgentSession(raw, currentProjectId, index);
      if (!session) return null;
      return conversationRecentAgentTargetFromSession(session, currentProjectId);
    }

    function conversationRecentAgentTone(raw) {
      const target = normalizeMentionTargetItem(raw);
      const key = String(mentionTargetKey(target) || mentionInsertLabel(target) || "").trim();
      const tones = ["tone-blue", "tone-green", "tone-orange", "tone-violet", "tone-slate"];
      if (!key) return tones[0];
      let hash = 0;
      for (let i = 0; i < key.length; i += 1) hash = ((hash * 33) + key.charCodeAt(i)) >>> 0;
      return tones[hash % tones.length];
    }

    function conversationRecentAgentInitial(raw) {
      const label = String(mentionInsertLabel(raw) || (raw && (raw.display_name || raw.channel_name)) || "").trim();
      return label.slice(0, 1) || "?";
    }

    function conversationRecentAgentSourceLabel(raw) {
      const kind = String(raw || "").trim().toLowerCase();
      return ({
        mention: "协同提及",
        sender: "消息发送方",
        source_ref: "来源回指",
        callback_to: "回执指向",
      })[kind] || "会话出现";
    }

    function getConversationRecentAgentStateByKey(key) {
      const draftKey = String(key || "").trim();
      if (!draftKey) return { count: 0, items: [], updatedAt: "" };
      const hit = PCONV.recentAgentsBySessionKey[draftKey];
      if (hit && typeof hit === "object") return hit;
      return { count: 0, items: [], updatedAt: "" };
    }

    function isConversationRecentAgentExpandedByKey(key) {
      const draftKey = String(key || "").trim();
      if (!draftKey) return false;
      return !!PCONV.recentAgentExpandedBySessionKey[draftKey];
    }

    function setConversationRecentAgentExpandedByKey(key, expanded) {
      const draftKey = String(key || "").trim();
      if (!draftKey) return;
      if (expanded) PCONV.recentAgentExpandedBySessionKey[draftKey] = true;
      else delete PCONV.recentAgentExpandedBySessionKey[draftKey];
    }

    function isConversationRecentAgentsEnabled() {
      return PCONV.recentAgentsEnabled !== false;
    }

    function renderConversationRecentAgentsToggleByKey(key) {
      const { recentAgentToggle } = convComposerUiElements();
      const draftKey = String(key || "").trim();
      const countEl = recentAgentToggle ? recentAgentToggle.querySelector(".convrecentagents-global-toggle-count") : null;
      if (!recentAgentToggle) return;
      if (!draftKey) {
        recentAgentToggle.style.display = "none";
        recentAgentToggle.classList.remove("active");
        recentAgentToggle.removeAttribute("aria-pressed");
        recentAgentToggle.title = "切换最近联系显示";
        recentAgentToggle.setAttribute("aria-label", "切换最近联系显示");
        if (countEl) {
          countEl.hidden = true;
          countEl.textContent = "";
        }
        return;
      }
      const state = getConversationRecentAgentStateByKey(draftKey);
      const rawCount = Number(state.count || 0);
      const count = Number.isFinite(rawCount) && rawCount > 0 ? Math.floor(rawCount) : 0;
      const countLabel = count > 99 ? "99+" : String(count);
      const enabled = isConversationRecentAgentsEnabled();
      recentAgentToggle.style.display = "";
      recentAgentToggle.classList.toggle("active", enabled);
      recentAgentToggle.setAttribute("aria-pressed", enabled ? "true" : "false");
      recentAgentToggle.title = count > 0
        ? (enabled ? `已显示最近联系（${countLabel}）` : `已隐藏最近联系（${countLabel}）`)
        : (enabled ? "已显示最近联系，点击隐藏" : "已隐藏最近联系，点击显示");
      recentAgentToggle.setAttribute("aria-label", count > 0
        ? (enabled ? `隐藏最近联系，当前 ${countLabel} 人` : `显示最近联系，当前 ${countLabel} 人`)
        : (enabled ? "隐藏最近联系" : "显示最近联系"));
      if (countEl) {
        countEl.hidden = count <= 0;
        countEl.textContent = count > 0 ? countLabel : "";
      }
    }

    function collectConversationRecentAgents(ctx, runs) {
      if (!ctx || !ctx.projectId || !ctx.sessionId) return [];
      const currentProjectId = String(ctx.projectId || "").trim();
      const currentSessionId = String(ctx.sessionId || "").trim().toLowerCase();
      const index = buildConversationRecentAgentDirectoryIndex(currentProjectId);
      const map = new Map();
      const push = (raw, meta = {}, seenInRun = null) => {
        const session = resolveConversationRecentAgentSession(raw, currentProjectId, index);
        if (!session) return;
        const target = conversationRecentAgentTargetFromSession(session, currentProjectId);
        if (!target) return;
        const targetSessionId = String(getSessionId(session) || target.session_id || "").trim().toLowerCase();
        if (!targetSessionId || targetSessionId === currentSessionId) return;
        const agentKey = mentionTargetKey(target);
        if (!agentKey) return;
        if (seenInRun && seenInRun.has(agentKey)) return;
        if (seenInRun) seenInRun.add(agentKey);
        const createdAt = String(meta.createdAt || "").trim();
        const currentTimeNum = toTimeNum(createdAt);
        let item = map.get(agentKey);
        if (!item) {
          item = {
            agentKey,
            target,
            session,
            displayName: String(conversationAgentName(session) || mentionInsertLabel(target) || target.display_name || target.channel_name || "协同对象").trim(),
            mentionCount: 0,
            firstSeenAt: createdAt,
            lastSeenAt: createdAt,
            lastSourceKind: "",
            lastMessageKind: "",
            lastSenderType: "",
          };
          map.set(agentKey, item);
        }
        item.target = target;
        item.session = session;
        item.displayName = String(conversationAgentName(session) || item.displayName || "").trim() || item.displayName;
        item.mentionCount += 1;
        const prevFirstNum = toTimeNum(item.firstSeenAt);
        if (createdAt && (prevFirstNum < 0 || (currentTimeNum >= 0 && currentTimeNum < prevFirstNum))) {
          item.firstSeenAt = createdAt;
        }
        const prevLastNum = toTimeNum(item.lastSeenAt);
        if (!item.lastSeenAt || prevLastNum < 0 || (currentTimeNum >= 0 && currentTimeNum >= prevLastNum)) {
          item.lastSeenAt = createdAt;
          item.lastSourceKind = String(meta.sourceKind || "").trim();
          item.lastMessageKind = String(meta.messageKind || "").trim();
          item.lastSenderType = String(meta.senderType || "").trim();
        }
      };

      (Array.isArray(runs) ? runs : []).forEach((run) => {
        const rid = String((run && run.id) || "").trim();
        const detail = rid ? (PCONV.detailMap[rid] || null) : null;
        const senderRun = mergeRunForDisplay(
          (detail && detail.full && detail.full.run && typeof detail.full.run === "object") ? detail.full.run : null,
          run
        );
        const spec = readConversationSpecFields(senderRun);
        const createdAt = String(firstNonEmptyText([run && run.createdAt, senderRun && senderRun.createdAt]) || "").trim();
        const userText = (detail && detail.full && detail.full.message)
          ? String(detail.full.message)
          : String((run && run.messagePreview) || "");
        const seenInRun = new Set();
        collectRunMentionTargets(senderRun, detail, userText).forEach((target) => {
          push(target, {
            createdAt,
            sourceKind: "mention",
            messageKind: spec.messageKind,
            senderType: spec.senderType,
          }, seenInRun);
        });
        [spec.sourceRef, spec.callbackTo].forEach((ref, order) => {
          push(ref, {
            createdAt,
            sourceKind: order === 0 ? "source_ref" : "callback_to",
            messageKind: spec.messageKind,
            senderType: spec.senderType,
          }, seenInRun);
        });
        if (String(spec.senderType || "").trim().toLowerCase() === "agent") {
          const senderSessionId = String(spec.senderId || "").trim();
          push({
            session_id: senderSessionId,
            sender_id: senderSessionId,
            display_name: String(spec.senderName || "").trim(),
            sender_name: String(spec.senderName || "").trim(),
            channel_name: String(senderSessionId ? findSessionChannelById(senderSessionId) : "").trim(),
            project_id: currentProjectId,
          }, {
            createdAt,
            sourceKind: "sender",
            messageKind: spec.messageKind,
            senderType: spec.senderType,
          }, seenInRun);
        }
      });

      return filterConversationRecentAgentItems(Array.from(map.values()), currentProjectId).sort((a, b) => {
        const ta = toTimeNum(a.lastSeenAt);
        const tb = toTimeNum(b.lastSeenAt);
        if (ta >= 0 && tb >= 0 && ta !== tb) return tb - ta;
        if (Number(a.mentionCount || 0) !== Number(b.mentionCount || 0)) {
          return Number(b.mentionCount || 0) - Number(a.mentionCount || 0);
        }
        return String(a.displayName || "").localeCompare(String(b.displayName || ""), "zh-Hans-CN");
      });
    }

    function buildConversationRecentAgentTitle(item) {
      const target = item && item.target;
      const session = item && item.session;
      if (!target) return "";
      const displayName = agentDisplayTitle(session || target, "协同对象");
      const displaySubmeta = agentDisplaySubtitle(session || target, { includeSessionIdFallback: true });
      const info = [];
      const when = compactDateTime(item.lastSeenAt || item.firstSeenAt || "");
      if (when) info.push("最近 " + when);
      const sourceText = conversationRecentAgentSourceLabel(item.lastSourceKind);
      if (sourceText) info.push(sourceText);
      if (Number(item.mentionCount || 0) > 1) info.push("出现 " + Number(item.mentionCount || 0) + " 次");
      return [
        displayName,
        displaySubmeta,
        info.join(" · "),
      ].filter(Boolean).join("\n");
    }

    function insertConversationRecentAgent(target) {
      const mention = normalizeMentionTargetItem(target);
      const draftKey = String(PCONV.composerBoundDraftKey || currentConvComposerDraftKey() || "").trim();
      if (!mention || !draftKey) return false;
      const exists = getConvComposerMentionsForCurrentSession().some((it) => mentionTargetKey(it) === mentionTargetKey(mention));
      if (exists) {
        const { input } = convComposerUiElements();
        if (input) {
          try { input.focus(); } catch (_) {}
        }
        renderConversationRecentAgentsByKey(draftKey);
        return true;
      }
      const result = insertMentionToComposerInput(mention);
      if (result && result.ok) {
        setHintText("conv", "已插入协同对象：@" + String(result.label || mentionInsertLabel(mention) || ""));
        return true;
      }
      return false;
    }

    function buildConversationRecentAgentChip(item) {
      const target = item && item.target;
      const session = item && item.session;
      if (!target) return null;
      const currentMentions = getConvComposerMentionsForCurrentSession();
      const active = currentMentions.some((it) => mentionTargetKey(it) === mentionTargetKey(target));
      const displayTitle = agentDisplayTitle(session || target, "协同对象");
      const displaySubmeta = agentDisplaySubtitle(session || target, { includeSessionIdFallback: true });
      const chipBtn = el("button", {
        class: "convrecentagent-chip" + (active ? " active" : ""),
        type: "button",
        title: buildConversationRecentAgentTitle(item),
      });
      if (session && typeof buildConversationAvatarNode === "function") {
        chipBtn.appendChild(buildConversationAvatarNode(session));
      } else {
        chipBtn.appendChild(el("span", {
          class: "convrecentagent-avatar " + conversationRecentAgentTone(target),
          text: conversationRecentAgentInitial(target),
        }));
      }
      const textWrap = el("span", { class: "convrecentagent-text" });
      textWrap.appendChild(el("span", {
        class: "convrecentagent-label",
        text: displayTitle,
      }));
      if (displaySubmeta) {
        textWrap.appendChild(el("span", {
          class: "convrecentagent-submeta",
          text: displaySubmeta,
        }));
      }
      chipBtn.appendChild(textWrap);
      chipBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        insertConversationRecentAgent(target);
      });
      return chipBtn;
    }

    function renderConversationRecentAgentsByKey(key) {
      const { recentAgentContainer } = convComposerUiElements();
      const draftKey = String(key || "").trim();
      if (!recentAgentContainer) return;
      renderConversationRecentAgentsToggleByKey(draftKey);
      recentAgentContainer.innerHTML = "";
      if (!draftKey) {
        recentAgentContainer.style.display = "none";
        return;
      }
      if (!isConversationRecentAgentsEnabled()) {
        recentAgentContainer.style.display = "none";
        setConversationRecentAgentExpandedByKey(draftKey, false);
        return;
      }
      const state = getConversationRecentAgentStateByKey(draftKey);
      const projectId = String((draftKey.split("::")[0] || STATE.project || "")).trim();
      const items = filterConversationRecentAgentItems(state.items, projectId);
      if (items.length !== (Array.isArray(state.items) ? state.items.length : 0)) {
        PCONV.recentAgentsBySessionKey[draftKey] = Object.assign({}, state, {
          count: items.length,
          items: items.slice(),
          updatedAt: new Date().toISOString(),
        });
      }
      if (!items.length) {
        recentAgentContainer.style.display = "none";
        return;
      }
      recentAgentContainer.style.display = "block";
      const wrap = el("div", { class: "convrecentagents-wrap" });
      const popover = el("div", { class: "convrecentagents-popover" });
      popover.hidden = true;
      const popoverList = el("div", { class: "convrecentagents-list" });
      items.forEach((item) => {
        const chipBtn = buildConversationRecentAgentChip(item);
        if (chipBtn) popoverList.appendChild(chipBtn);
      });
      popover.appendChild(popoverList);
      wrap.appendChild(popover);

      const bar = el("div", { class: "convrecentagents-bar" });
      const strip = el("div", { class: "convrecentagents-strip" });
      items.forEach((item) => {
        const chipBtn = buildConversationRecentAgentChip(item);
        if (chipBtn) strip.appendChild(chipBtn);
      });
      bar.appendChild(strip);
      wrap.appendChild(bar);
      recentAgentContainer.appendChild(wrap);

      const allowExpand = items.length > 1 && strip.scrollWidth > (strip.clientWidth + 4);
      if (!allowExpand) {
        setConversationRecentAgentExpandedByKey(draftKey, false);
        popover.hidden = true;
        return;
      }

      const expanded = isConversationRecentAgentExpandedByKey(draftKey);
      if (expanded) {
        wrap.classList.add("is-expanded");
        popover.hidden = false;
      }
      {
        const toggleBtn = el("button", {
          class: "btn textbtn convrecentagents-toggle" + (expanded ? " active" : ""),
          type: "button",
          text: expanded ? "收起" : ("展开 " + items.length),
        });
        toggleBtn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          setConversationRecentAgentExpandedByKey(draftKey, !expanded);
          renderConversationRecentAgentsByKey(draftKey);
        });
        bar.appendChild(toggleBtn);
      }
    }

    function refreshConversationRecentAgentsFromRuns(ctx, runs) {
      const draftKey = ctx ? convComposerDraftKey(ctx.projectId, ctx.sessionId) : "";
      if (!draftKey) {
        renderConversationRecentAgentsByKey("");
        return;
      }
      const items = collectConversationRecentAgents(ctx, runs);
      PCONV.recentAgentsBySessionKey[draftKey] = {
        count: items.length,
        items,
        updatedAt: new Date().toISOString(),
      };
      renderConversationRecentAgentsByKey(draftKey);
    }

    const CONVERSATION_AGENT_TRAINING_PREFIX = "[Agent培训]";
    const LEGACY_CONVERSATION_AGENT_INIT_PREFIX = "[Qoreon]";
    const CONVERSATION_AGENT_INIT_LEAD = "在开始当前协作前，你必须先完成以下初始化训练。未完成前，不要回复“已完成初始化”，也不要直接开始正式任务。";

    function normalizeConversationInitChannelLabel(channelName) {
      const label = String(channelName || "").trim();
      return label || "当前通道";
    }

    function buildUnifiedAgentInitMessage(channelName) {
      const channelLabel = normalizeConversationInitChannelLabel(channelName);
      return [
        CONVERSATION_AGENT_TRAINING_PREFIX + " " + channelLabel,
        CONVERSATION_AGENT_INIT_LEAD,
        "",
        "1. 明确职责边界",
        "- 只围绕当前通道和当前任务主线执行，不自行扩题。",
        "- 默认处理后回原发送 Agent；若消息中有 callback_to.session_id，优先回该 session。",
        "",
        "2. 对齐项目真源",
        "- 项目配置 = 真源默认上下文。",
        "- Agent = 身份，session = 当前承载结果。",
        "- 不清楚工作区、分支、真源时，先查项目内真源，不自行猜测。",
        "",
        "3. 阅读必读入口并学习项目技能",
        "- README.md",
        "- 活动任务/",
        "- 活动反馈/",
        "- 产出物/材料/",
        "- 产出物/沉淀/",
        "- 当前项目 skills 真源/索引文件",
        "- 至少重点学习：agent-init-training-playbook、collab-message-send（或当前项目等效的正式消息技能）、当前通道自己的专项 skill。",
        "",
        "4. 学会怎么发正式消息",
        "- 跨 Agent / 跨通道协作只能走同源 /api/codex/announce（announce_to_channel），不能把内部草稿、内部 spawn、非正式 resume 当成“已通知通道”。",
        "- 正式消息默认用你当前执行 Agent 自己的身份发送，不借用项目主会话、总控或其他通道 Agent 身份。",
        "- 没有 announce_run_id 时，不得写已发出 / 已送达 / 已通知通道。",
        "- 正式通知成功至少分三层判断：已生成待发送正文 / 已提交发送，待验证 / 已完成证据闭环。",
        "",
        "5. 学会什么时候必须回执",
        "- 收到任务先首回执，执行后再回结构化结论。",
        "- 只有 notify_only 才可不回。",
        "- 后续默认按 任务 / 反馈 / 产出物 推进；普通任务优先任务文件收口块，反馈文件仅用于增强验收包。",
        "",
        "6. 完成一次消息能力验证",
        "- 去项目通讯录/CCR 中找到一个“不是你自己”的 Agent，发送 1 条最小初始化验证消息。",
        "- 如果当前项目没有可用通讯录或找不到目标，再回唯一阻塞，不得跳过这一步。",
        "",
        "7. 学习完成后的固定回执格式",
        "已完成初始化",
        "当前职责边界: <一句话>",
        "当前主线: <一句话>",
        "已学习技能: <列出本轮已学习的关键 skills>",
        "通讯录验证: 已向 <agent名称> 发送正式消息",
        "验证证据: <run_id / 目标session_id>",
        "唯一阻塞: <无/一句话>",
        "首个动作: <一句话>",
      ].join("\n");
    }

    function isUnifiedAgentInitMessageText(text) {
      const raw = String(text || "").trim();
      if (!raw) return false;
      if (raw.startsWith(CONVERSATION_AGENT_TRAINING_PREFIX)) return true;
      if (!raw.startsWith(LEGACY_CONVERSATION_AGENT_INIT_PREFIX)) return false;
      return raw.includes(CONVERSATION_AGENT_INIT_LEAD);
    }

    function getConversationTrainingSentAtByKey(key) {
      const draftKey = String(key || "").trim();
      if (!draftKey) return "";
      return String(PCONV.trainingSentBySessionKey[draftKey] || "").trim();
    }

    function setConversationTrainingSentByKey(key, sentAt) {
      const draftKey = String(key || "").trim();
      if (!draftKey) return;
      const text = String(sentAt === true ? new Date().toISOString() : (sentAt || "")).trim();
      if (!text) delete PCONV.trainingSentBySessionKey[draftKey];
      else PCONV.trainingSentBySessionKey[draftKey] = text;
      persistSessionScopedMap(CONV_TRAINING_SENT_KEY, PCONV.trainingSentBySessionKey);
    }

    function isConversationTrainingDismissedByKey(key) {
      const draftKey = String(key || "").trim();
      if (!draftKey) return false;
      return !!PCONV.trainingDismissedBySessionKey[draftKey];
    }

    function setConversationTrainingDismissedByKey(key, dismissed) {
      const draftKey = String(key || "").trim();
      if (!draftKey) return;
      if (dismissed) PCONV.trainingDismissedBySessionKey[draftKey] = true;
      else delete PCONV.trainingDismissedBySessionKey[draftKey];
    }

    function isConversationTrainingManualOpenByKey(key) {
      const draftKey = String(key || "").trim();
      if (!draftKey) return false;
      return !!PCONV.trainingManualOpenBySessionKey[draftKey];
    }

    function setConversationTrainingManualOpenByKey(key, open) {
      const draftKey = String(key || "").trim();
      if (!draftKey) return;
      if (open) PCONV.trainingManualOpenBySessionKey[draftKey] = true;
      else delete PCONV.trainingManualOpenBySessionKey[draftKey];
    }

    function conversationTrainingVisibleMessageCount(runs) {
      return (Array.isArray(runs) ? runs : [])
        .filter((run) => !!String((run && run.id) || "").trim())
        .length;
    }

    function conversationTrainingRemainingCount(runs) {
      return Math.max(0, 3 - conversationTrainingVisibleMessageCount(runs));
    }

    function conversationTrainingTextFromRun(run, detail) {
      return String(firstNonEmptyText([
        detail && detail.full && detail.full.message,
        run && run.message,
        run && run.messagePreview,
        run && run.lastMessage,
        run && run.partialMessage,
      ]) || "").trim();
    }

    function findConversationTrainingMessageSentAt(runs) {
      const list = Array.isArray(runs) ? runs : [];
      for (let i = list.length - 1; i >= 0; i -= 1) {
        const run = list[i] || {};
        const rid = String(run.id || "").trim();
        const detail = rid ? (PCONV.detailMap[rid] || null) : null;
        const text = conversationTrainingTextFromRun(run, detail);
        if (!isUnifiedAgentInitMessageText(text)) continue;
        return String(firstNonEmptyText([
          run.createdAt,
          detail && detail.full && detail.full.run && detail.full.run.createdAt,
        ]) || "history").trim();
      }
      return "";
    }

    function buildConversationTrainingMessage(channelName) {
      return buildUnifiedAgentInitMessage(channelName);
    }

    function currentConversationTrainingRuns(ctx) {
      const context = (ctx && typeof ctx === "object") ? ctx : currentConversationCtx();
      if (!context) return [];
      const timelineKey = String(context.projectId || STATE.project || "") + "::" + String(context.sessionId || "").trim();
      return resolveConversationRunsBySessionKey(timelineKey, context.sessionId).slice();
    }

    function renderConversationTrainingReopenButtonState(button, opts = {}) {
      if (!button) return;
      const visible = !!opts.visible;
      const dismissed = !!opts.dismissed;
      const showing = !!opts.showing;
      const sending = !!opts.sending;
      const completed = !!opts.completed;
      button.style.display = visible ? "" : "none";
      button.disabled = !visible || !!sending;
      button.classList.toggle("active", visible && (showing || dismissed));
      button.setAttribute("aria-hidden", visible ? "false" : "true");
      let label = "查看 Agent 培训";
      if (showing) label = "Agent 培训已显示";
      else if (completed) label = "查看已发送的 Agent 培训";
      else if (dismissed) label = "重新显示 Agent 培训";
      button.title = label;
      button.setAttribute("aria-label", label);
    }

    function renderConversationTrainingPrompt(ctx, runs, opts = {}) {
      const {
        trainingContainer,
        trainingCount,
        trainingDesc,
        trainingSendBtn,
        trainingCloseBtn,
        trainingReopenBtn,
      } = convComposerUiElements();
      const timeline = document.getElementById("convTimeline");
      const trainingDock = document.getElementById("convTrainingDock");
      const convWrap = document.getElementById("convWrap");
      const composer = convWrap ? convWrap.querySelector(".convcomposer") : null;
      const timelineReady = opts && Object.prototype.hasOwnProperty.call(opts, "timelineReady")
        ? !!opts.timelineReady
        : true;
      if (!trainingContainer) {
        renderConversationTrainingReopenButtonState(trainingReopenBtn, { visible: false });
        return;
      }
      const draftKey = ctx ? convComposerDraftKey(ctx.projectId, ctx.sessionId) : "";
      if (!draftKey) {
        renderConversationTrainingReopenButtonState(trainingReopenBtn, { visible: false });
        trainingContainer.style.display = "none";
        if (trainingDock) trainingDock.classList.remove("show");
        if (convWrap) convWrap.style.removeProperty("--conv-training-offset");
        if (timeline) timeline.classList.remove("has-training-banner");
        return;
      }
      if (!timelineReady) {
        renderConversationTrainingReopenButtonState(trainingReopenBtn, { visible: false });
        trainingContainer.style.display = "none";
        if (trainingDock) trainingDock.classList.remove("show");
        if (convWrap) convWrap.style.removeProperty("--conv-training-offset");
        if (timeline) timeline.classList.remove("has-training-banner");
        return;
      }
      const historySentAt = findConversationTrainingMessageSentAt(runs);
      if (historySentAt && !getConversationTrainingSentAtByKey(draftKey)) {
        setConversationTrainingSentByKey(draftKey, historySentAt);
      }
      const alreadySent = !!getConversationTrainingSentAtByKey(draftKey);
      const remaining = conversationTrainingRemainingCount(runs);
      const manualOpen = isConversationTrainingManualOpenByKey(draftKey);
      if (alreadySent && !manualOpen) setConversationTrainingDismissedByKey(draftKey, false);
      if (!alreadySent && remaining <= 0 && !manualOpen) setConversationTrainingDismissedByKey(draftKey, false);
      const dismissed = isConversationTrainingDismissedByKey(draftKey);
      const shouldShow = manualOpen || (!alreadySent && !dismissed && remaining > 0);
      renderConversationTrainingReopenButtonState(trainingReopenBtn, {
        visible: true,
        dismissed,
        showing: shouldShow,
        completed: alreadySent,
        sending: !!PCONV.sending,
      });
      trainingContainer.style.display = shouldShow ? "flex" : "none";
      if (trainingDock) trainingDock.classList.toggle("show", shouldShow);
      if (convWrap) {
        if (shouldShow && composer) {
          const composerHeight = Math.ceil(composer.getBoundingClientRect().height || composer.offsetHeight || 0);
          convWrap.style.setProperty("--conv-training-offset", Math.max(composerHeight + 4, 126) + "px");
        } else {
          convWrap.style.removeProperty("--conv-training-offset");
        }
      }
      if (timeline) timeline.classList.toggle("has-training-banner", shouldShow);
      if (!shouldShow) return;
      if (trainingCount) {
        if (alreadySent) trainingCount.textContent = "已发送";
        else if (remaining > 0) trainingCount.textContent = "再 " + remaining + " 条消息后自动消失";
        else trainingCount.textContent = "已手动显示";
      }
      if (trainingDesc) {
        trainingDesc.textContent = alreadySent
          ? "Agent 培训已发送，可在上方消息记录中查看执行结果。"
          : "新 Agent 开始协作前，先完成初始化：对齐项目真源、阅读入口、确认正式消息门禁与回执口径。";
      }
      if (trainingSendBtn) {
        trainingSendBtn.disabled = alreadySent || !!PCONV.sending;
        trainingSendBtn.textContent = alreadySent ? "已发送" : (PCONV.sending ? "发送中..." : "发送培训");
      }
      if (trainingCloseBtn) {
        trainingCloseBtn.disabled = !!PCONV.sending;
      }
    }

    function dismissConversationTrainingPrompt() {
      const ctx = currentConversationCtx();
      const draftKey = ctx ? convComposerDraftKey(ctx.projectId, ctx.sessionId) : "";
      if (!ctx || !draftKey) return;
      setConversationTrainingManualOpenByKey(draftKey, false);
      setConversationTrainingDismissedByKey(draftKey, true);
      renderConversationTrainingPrompt(ctx, currentConversationTrainingRuns(ctx), { timelineReady: true });
    }

    function reopenConversationTrainingPrompt() {
      const ctx = currentConversationCtx();
      const draftKey = ctx ? convComposerDraftKey(ctx.projectId, ctx.sessionId) : "";
      if (!ctx || !draftKey) return;
      const runs = currentConversationTrainingRuns(ctx);
      setConversationTrainingManualOpenByKey(draftKey, true);
      setConversationTrainingDismissedByKey(draftKey, false);
      renderConversationTrainingPrompt(ctx, runs, { timelineReady: true });
    }

    async function sendConversationTrainingMessage() {
      const ctx = currentConversationCtx();
      const draftKey = ctx ? convComposerDraftKey(ctx.projectId, ctx.sessionId) : "";
      if (!ctx || !draftKey || PCONV.sending) return false;
      if (getConversationTrainingSentAtByKey(draftKey)) return false;
      const sentOk = await sendConversationQuickMessage(buildConversationTrainingMessage(ctx.channelName), {
        pendingHint: "发送中（Agent培训）…",
        successHint: "已发送 Agent 培训，等待执行回溯刷新…",
        onSuccess: () => {
          setConversationTrainingManualOpenByKey(draftKey, false);
          setConversationTrainingDismissedByKey(draftKey, false);
          setConversationTrainingSentByKey(draftKey, true);
        },
      });
      if (sentOk) renderConversationTrainingPrompt(ctx, currentConversationTrainingRuns(ctx), { timelineReady: true });
      return sentOk;
    }

    function mentionLabelCandidates(rawMention) {
      const m = normalizeMentionTargetItem(rawMention);
      if (!m) return [];
      const out = [];
      const seen = new Set();
      [
        mentionInsertLabel(m),
        globalMentionScopedLabel(m),
        String(m.display_name || "").trim(),
        String(m.channel_name || "").trim(),
        sanitizeMentionLabelSegment(String(m.project_id || "").trim())
          ? (sanitizeMentionLabelSegment(String(m.project_id || "").trim()) + "/" + sanitizeMentionLabelSegment(mentionBaseLabel(m)))
          : "",
      ].forEach((name) => {
        const label = String(name || "").trim();
        if (!label) return;
        const key = label.toLowerCase();
        if (seen.has(key)) return;
        seen.add(key);
        out.push(label);
      });
      return out;
    }

    function removeMentionTokensFromText(text, rawMention) {
      let out = String(text || "");
      const labels = mentionLabelCandidates(rawMention);
      if (!out || !labels.length) return out;
      labels.forEach((label) => {
        const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        const re = new RegExp("(^|" + CONV_MENTION_BOUNDARY + ")@" + escaped + "(?=$|" + CONV_MENTION_BOUNDARY + ")", "g");
        out = out.replace(re, (_, prefix) => String(prefix || ""));
      });
      return out
        .replace(/[ \t]{2,}/g, " ")
        .replace(/[ \t]+\n/g, "\n")
        .replace(/\n{3,}/g, "\n\n");
    }

    function extractMentionLabelsFromText(text) {
      const src = String(text || "");
      if (!src) return [];
      const out = [];
      CONV_MENTION_TOKEN_RE.lastIndex = 0;
      let m = null;
      while ((m = CONV_MENTION_TOKEN_RE.exec(src))) {
        const label = String((m && m[1]) || "").trim();
        if (!label) continue;
        out.push(label);
      }
      CONV_MENTION_TOKEN_RE.lastIndex = 0;
      return out;
    }

    function deriveConvComposerMentionTargetsFromText(text, projectId) {
      const labels = extractMentionLabelsFromText(text);
      if (!labels.length) return [];
      const index = new Map();
      const aliases = [];
      const register = (it) => {
        const target = normalizeMentionTargetItem(it);
        if (!target) return;
        const names = [
          mentionInsertLabel(target),
          globalMentionScopedLabel(target),
          String(target.display_name || "").trim(),
          String(target.channel_name || "").trim(),
        ];
        names.forEach((raw) => {
          const name = String(raw || "").trim().toLowerCase();
          if (!name || index.has(name)) return;
          index.set(name, target);
          aliases.push(name);
        });
      };
      conversationMentionDirectory(projectId).forEach(register);
      conversationGlobalMentionDirectory(projectId).forEach(register);
      aliases.sort((a, b) => b.length - a.length);
      const out = [];
      const seen = new Set();
      labels.forEach((raw) => {
        const key = String(raw || "").trim().toLowerCase();
        if (!key) return;
        let hit = index.get(key);
        if (!hit) {
          const prefix = aliases.find((alias) => key.startsWith(alias));
          if (prefix) hit = index.get(prefix);
        }
        if (!hit) return;
        const explicitScopedLabel = String(raw || "").trim();
        if (explicitScopedLabel && explicitScopedLabel.includes("/")) {
          hit = Object.assign({}, hit, {
            mention_label: explicitScopedLabel,
          });
        }
        const mentionKey = mentionTargetKey(hit);
        if (!mentionKey || seen.has(mentionKey)) return;
        seen.add(mentionKey);
        out.push(hit);
      });
      return cloneConvComposerMentionTargets(out);
    }

    function syncConvComposerMentionsByKeyFromText(key, text) {
      const draftKey = String(key || "").trim();
      if (!draftKey) return [];
      const nextText = String(text || "");
      const mentions = deriveConvComposerMentionTargetsFromText(nextText, STATE.project);
      updateConvComposerDraftByKey(draftKey, (d) => {
        d.text = nextText;
        d.mentions = mentions;
      });
      return mentions;
    }

    function insertMentionToComposerInput(rawMention, opts = {}) {
      const mention = normalizeMentionTargetItem(rawMention);
      if (!mention) return { ok: false, added: false, label: "" };
      const key = String(PCONV.composerBoundDraftKey || currentConvComposerDraftKey() || "").trim();
      const { input } = convComposerUiElements();
      if (!key || !input) return { ok: false, added: false, label: "" };
      const st = (opts && typeof opts === "object") ? opts : {};
      const src = String(input.value || "");
      const selStartRaw = input.selectionStart;
      const selEndRaw = input.selectionEnd;
      const defaultPos = (typeof selStartRaw === "number" && selStartRaw >= 0) ? selStartRaw : src.length;
      const useAnchor = st.useAnchor === true;
      const anchorStart = useAnchor ? Number(st.anchorStart) : defaultPos;
      const anchorEnd = useAnchor
        ? Number(st.anchorEnd)
        : ((typeof selEndRaw === "number" && selEndRaw >= 0) ? selEndRaw : defaultPos);
      const start = Math.max(0, Math.min(src.length, Number.isFinite(anchorStart) ? anchorStart : defaultPos));
      const end = Math.max(start, Math.min(src.length, Number.isFinite(anchorEnd) ? anchorEnd : start));
      const before = src.slice(0, start);
      const after = src.slice(end);
      const label = mentionInsertLabel(mention) || "协同对象";
      const token = "@" + label;
      const needsLeftSpace = !!before && /[0-9A-Za-z_@]$/.test(before);
      const needsRightSpace = !!after && /^[0-9A-Za-z_@]/.test(after);
      const insertText = (needsLeftSpace ? " " : "") + token + (needsRightSpace ? " " : "");
      const nextText = before + insertText + after;
      input.value = nextText;
      try {
        const cursor = Math.max(0, Math.min(nextText.length, before.length + insertText.length));
        input.setSelectionRange(cursor, cursor);
      } catch (_) {}
      const mentions = syncConvComposerMentionsByKeyFromText(key, nextText);
      const added = mentions.some((it) => mentionTargetKey(it) === mentionTargetKey(mention));
      renderConvComposerMentionsByKey(key);
      if (typeof input.__adjustHeight === "function") input.__adjustHeight();
      else setMessageInputHeight(input);
      hideConvMentionSuggest();
      try { input.focus(); } catch (_) {}
      return { ok: true, added, label };
    }

    function parseConvMentionAnchor(text, caret) {
      const src = String(text || "");
      const pos = Math.max(0, Number(caret || 0));
      const prefix = src.slice(0, pos);
      const lastAt = prefix.lastIndexOf("@");
      if (lastAt < 0) return null;
      let start = lastAt;
      let mode = currentProjectMentionSuggestMode();
      if (lastAt > 0 && prefix.charAt(lastAt - 1) === "@") {
        start = lastAt - 1;
        mode = globalProjectMentionSuggestMode();
      }
      const before = start > 0 ? prefix.charAt(start - 1) : "";
      if (before && /[0-9A-Za-z_@]/.test(before)) return null;
      const token = prefix.slice(start, pos);
      if (!token) return null;
      const marker = mode === globalProjectMentionSuggestMode() ? "@@" : "@";
      if (!token.startsWith(marker)) return null;
      const query = String(token.slice(marker.length) || "");
      if (query.length > 48) return null;
      if (/\s/.test(query)) return null;
      return {
        mode,
        start,
        end: pos,
        query,
      };
    }

    function hideConvMentionSuggest() {
      PCONV.mentionSuggest = emptyConvMentionSuggestState();
      const { mentionSuggest } = convComposerUiElements();
      if (mentionSuggest) {
        mentionSuggest.innerHTML = "";
        mentionSuggest.style.display = "none";
      }
    }

    function applyMentionCandidateToComposer(candidate) {
      const mention = normalizeMentionTargetItem(candidate);
      if (!mention) return false;
      const st = PCONV.mentionSuggest || {};
      const result = insertMentionToComposerInput(mention, {
        useAnchor: true,
        anchorStart: Number(st.anchorStart),
        anchorEnd: Number(st.anchorEnd),
      });
      if (!result.ok) return false;
      setHintText("conv", "已插入协同对象：@" + String(result.label || mentionInsertLabel(mention) || ""));
      return true;
    }

    function mentionSearchHaystack(raw) {
      const m = normalizeMentionTargetItem(raw);
      if (!m) return "";
      return [
        m.display_name,
        m.channel_name,
        m.session_id,
        m.cli_type,
        m.project_name,
        m.project_id,
        mentionInsertLabel(m),
      ].map((part) => String(part || "").trim().toLowerCase()).filter(Boolean).join(" ");
    }

    function buildConvMentionGroups(candidates, currentProjectId) {
      const currentPid = String(currentProjectId || "").trim();
      const map = new Map();
      (Array.isArray(candidates) ? candidates : []).forEach((raw) => {
        const item = normalizeMentionTargetItem(raw);
        if (!item) return;
        const pid = String(item.project_id || "").trim();
        const title = mentionProjectLabel(pid, item.project_name) || "未归属项目";
        const mapKey = pid || title;
        if (!map.has(mapKey)) {
          map.set(mapKey, {
            projectId: pid,
            projectName: title,
            isCurrent: !!pid && pid === currentPid,
            items: [],
          });
        }
        map.get(mapKey).items.push(item);
      });
      const groups = Array.from(map.values());
      groups.sort((a, b) => {
        if (a.isCurrent && !b.isCurrent) return -1;
        if (b.isCurrent && !a.isCurrent) return 1;
        return String(a.projectName || "").localeCompare(String(b.projectName || ""), "zh-Hans-CN");
      });
      groups.forEach((group) => {
        group.items.sort((a, b) => String(a.display_name || "").localeCompare(String(b.display_name || ""), "zh-Hans-CN"));
      });
      return groups;
    }

    function convMentionMetaText(raw, mode) {
      const item = normalizeMentionTargetItem(raw);
      if (!item) return "";
      return agentDisplaySubtitle(item, { includeSessionIdFallback: true });
    }

    function buildConvMentionSuggestItem(it, mode, idx, activeIndex) {
      const item = el("button", {
        class: "convmention-item" + (idx === activeIndex ? " active" : ""),
        type: "button",
      });
      const main = el("span", { class: "convmention-main" });
      main.appendChild(el("span", { class: "convmention-name", text: agentDisplayTitle(it, "协同对象") }));
      const subMeta = convMentionMetaText(it, mode);
      if (subMeta) main.appendChild(el("span", { class: "convmention-submeta", text: subMeta }));
      item.appendChild(main);
      item.appendChild(el("span", {
        class: "convmention-meta",
        text: mode === globalProjectMentionSuggestMode()
          ? (mentionInsertLabel(it) || shortId(String(it.session_id || "")))
          : (shortId(String(it.session_id || "")) + " · " + String(it.cli_type || "codex")),
      }));
      item.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        applyMentionCandidateToComposer(it);
      });
      return item;
    }

    function renderConvMentionSuggest() {
      const st = PCONV.mentionSuggest || {};
      const { mentionSuggest } = convComposerUiElements();
      if (!mentionSuggest) return;
      if (!st.open || !Array.isArray(st.candidates) || st.candidates.length === 0) {
        mentionSuggest.innerHTML = "";
        mentionSuggest.style.display = "none";
        return;
      }
      mentionSuggest.innerHTML = "";
      if (String(st.mode || "") === globalProjectMentionSuggestMode()) {
        const head = el("div", { class: "convmention-head" });
        head.appendChild(el("div", { class: "convmention-kicker", text: "@@ 全局 Agent" }));
        const resultCount = Array.isArray(st.candidates) ? st.candidates.length : 0;
        const summary = (Array.isArray(st.groups) && st.groups.length)
          ? ("按项目分组 · " + st.groups.length + " 个项目 · " + resultCount + " 条候选")
          : ("全局搜索 · " + resultCount + " 条候选");
        head.appendChild(el("div", { class: "convmention-summary", text: summary }));
        mentionSuggest.appendChild(head);
      }
      const list = el("div", { class: "convmention-list" });
      const activeIndex = Math.max(0, Math.min(Number(st.activeIndex || 0), st.candidates.length - 1));
      if (String(st.mode || "") === globalProjectMentionSuggestMode() && Array.isArray(st.groups) && st.groups.length) {
        let renderIndex = 0;
        st.groups.forEach((group) => {
          const section = el("div", { class: "convmention-group" });
          section.appendChild(el("div", {
            class: "convmention-group-title" + ((group && group.isCurrent) ? " is-current" : ""),
            text: String((group && group.projectName) || "未归属项目") + ((group && group.isCurrent) ? " · 当前项目" : ""),
          }));
          (Array.isArray(group && group.items) ? group.items : []).forEach((it) => {
            section.appendChild(buildConvMentionSuggestItem(it, st.mode, renderIndex, activeIndex));
            renderIndex += 1;
          });
          list.appendChild(section);
        });
      } else {
        st.candidates.forEach((it, idx) => {
          list.appendChild(buildConvMentionSuggestItem(it, st.mode, idx, activeIndex));
        });
      }
      mentionSuggest.appendChild(list);
      mentionSuggest.style.display = "block";
      const activeEl = list.querySelector(".convmention-item.active");
      if (activeEl && typeof activeEl.scrollIntoView === "function") {
        try {
          activeEl.scrollIntoView({ block: "nearest" });
        } catch (_) {
          try { activeEl.scrollIntoView(false); } catch (_) {}
        }
      }
    }

    function updateConvMentionSuggestByInput() {
      const key = String(PCONV.composerBoundDraftKey || currentConvComposerDraftKey() || "").trim();
      const { input } = convComposerUiElements();
      if (!key || !input) {
        hideConvMentionSuggest();
        return;
      }
      const caret = Number(input.selectionStart || 0);
      const anchor = parseConvMentionAnchor(String(input.value || ""), caret);
      if (!anchor) {
        hideConvMentionSuggest();
        return;
      }
      const query = String(anchor.query || "").trim().toLowerCase();
      const mode = String(anchor.mode || currentProjectMentionSuggestMode()) === globalProjectMentionSuggestMode()
        ? globalProjectMentionSuggestMode()
        : currentProjectMentionSuggestMode();
      if (mode === globalProjectMentionSuggestMode()) hydrateConversationGlobalMentionDirectory(STATE.project);
      const source = mode === globalProjectMentionSuggestMode()
        ? conversationGlobalMentionDirectory(STATE.project)
        : conversationMentionDirectory(STATE.project);
      const list = source.filter((it) => {
        if (!query) return true;
        return mentionSearchHaystack(it).includes(query);
      });
      if (!list.length) {
        hideConvMentionSuggest();
        return;
      }
      const prev = PCONV.mentionSuggest || {};
      let activeIndex = 0;
      if (prev.open && Array.isArray(prev.candidates) && prev.candidates.length) {
        const prevIdx = Math.max(0, Math.min(Number(prev.activeIndex || 0), prev.candidates.length - 1));
        const prevItem = prev.candidates[prevIdx];
        const prevKey = mentionTargetKey(prevItem);
        if (prevKey) {
          const nextIdx = list.findIndex((it) => mentionTargetKey(it) === prevKey);
          if (nextIdx >= 0) activeIndex = nextIdx;
        }
      }
      PCONV.mentionSuggest = {
        open: true,
        mode,
        query: anchor.query,
        activeIndex,
        anchorStart: anchor.start,
        anchorEnd: anchor.end,
        candidates: list,
        groups: mode === globalProjectMentionSuggestMode() ? buildConvMentionGroups(list, STATE.project) : [],
        draftKey: key,
      };
      renderConvMentionSuggest();
    }

    function handleConvMentionInputKeydown(e) {
      const key = String((e && e.key) || "");
      const st = PCONV.mentionSuggest || {};
      if (st.open && Array.isArray(st.candidates) && st.candidates.length > 0) {
        if (key === "ArrowDown") {
          e.preventDefault();
          e.stopPropagation();
          st.activeIndex = (Number(st.activeIndex || 0) + 1) % st.candidates.length;
          PCONV.mentionSuggest = st;
          renderConvMentionSuggest();
          return true;
        }
        if (key === "ArrowUp") {
          e.preventDefault();
          e.stopPropagation();
          st.activeIndex = (Number(st.activeIndex || 0) - 1 + st.candidates.length) % st.candidates.length;
          PCONV.mentionSuggest = st;
          renderConvMentionSuggest();
          return true;
        }
        if (key === "Escape") {
          e.preventDefault();
          e.stopPropagation();
          hideConvMentionSuggest();
          return true;
        }
        if (key === "Enter") {
          e.preventDefault();
          e.stopPropagation();
          const idx = Math.max(0, Math.min(Number(st.activeIndex || 0), st.candidates.length - 1));
          applyMentionCandidateToComposer(st.candidates[idx]);
          return true;
        }
      }
      if (key === "Backspace") {
        const { input } = convComposerUiElements();
        if (!input) return false;
        const start = (typeof input.selectionStart === "number") ? input.selectionStart : 0;
        const end = (typeof input.selectionEnd === "number") ? input.selectionEnd : 0;
        if (start === 0 && end === 0) {
          const mentions = getConvComposerMentionsForCurrentSession();
          if (mentions.length) {
            removeConvComposerMentionByKey(String(PCONV.composerBoundDraftKey || ""), mentions[mentions.length - 1]);
            e.preventDefault();
            e.stopPropagation();
            return true;
          }
        }
      }
      return false;
    }

    function serializeMentionTargetsForSend(list) {
      return cloneConvComposerMentionTargets(list).map((m) => {
        const row = {
          channel_name: String(m.channel_name || ""),
          session_id: String(m.session_id || ""),
          cli_type: String(m.cli_type || "codex") || "codex",
          display_name: String(m.display_name || m.channel_name || ""),
        };
        const projectId = String(m.project_id || "").trim();
        if (projectId) row.project_id = projectId;
        return row;
      });
    }

    function mentionCompatLine(targets) {
      const list = Array.isArray(targets) ? targets : [];
      if (!list.length) return "";
      const names = [];
      const seen = new Set();
      list.forEach((it) => {
        const nm = String(mentionInsertLabel(it) || (it && (it.display_name || it.channel_name)) || "").trim();
        if (!nm || seen.has(nm)) return;
        seen.add(nm);
        names.push(nm);
      });
      if (!names.length) return "";
      return "[协同对象: " + names.join("、") + "]";
    }

    function appendMentionCompatToMessage(message, targets) {
      const base = String(message || "").trim();
      const line = mentionCompatLine(targets);
      if (!line) return base;
      if (base.includes("[协同对象:")) return base;
      return base ? (base + "\n\n" + line) : line;
    }

    function extractMentionTargetsFromText(text) {
      const src = String(text || "");
      if (!src) return [];
      const m = src.match(/\[协同对象\s*:\s*([^\]]+)\]/);
      if (!m || !m[1]) return [];
      const out = [];
      const seen = new Set();
      String(m[1]).split(/[、,，]/).forEach((part) => {
        const nm = String(part || "").trim();
        if (!nm || seen.has(nm)) return;
        seen.add(nm);
        out.push({
          channel_name: nm,
          session_id: "",
          cli_type: "",
          display_name: nm,
        });
      });
      return out;
    }

    function applyConvComposerDraftToUiByKey(key, opts = {}) {
      const { input } = convComposerUiElements();
      if (!input) return;
      updateConvComposerDraftByKey(key, (d) => {
        stripReplyInjectedPrefixFromDraft(d);
      });
      const draft = getConvComposerDraftByKey(key);
      syncConvComposerMentionsByKeyFromText(key, draft.text || "");
      input.value = String(draft.text || "");
      if (typeof input.__adjustHeight === "function") input.__adjustHeight();
      else setMessageInputHeight(input);
      renderAttachments();
      renderConvComposerMentionsByKey(key);
      renderConvComposerReplyContextByKey(key);
      hideConvMentionSuggest();
      if (opts.focus) {
        try {
          input.focus();
          const len = input.value.length;
          input.setSelectionRange(len, len);
        } catch (_) {}
      }
    }

    function bindConvComposerToSelectedSession(opts = {}) {
      const nextKey = currentConvComposerDraftKey();
      const prevKey = String(PCONV.composerBoundDraftKey || "").trim();
      const force = !!opts.force;
      if (!force && nextKey === prevKey) return;
      saveConvComposerUiToBoundDraft();
      PCONV.composerBoundDraftKey = nextKey;
      applyConvComposerDraftToUiByKey(nextKey, opts);
    }

    function setConvComposerTextForCurrentSession(text) {
      const key = currentConvComposerDraftKey();
      if (!key) return;
      syncConvComposerMentionsByKeyFromText(key, text);
      if (String(PCONV.composerBoundDraftKey || "") === String(key)) {
        renderConvComposerMentionsByKey(key);
        renderConvComposerReplyContextByKey(key);
        if (typeof syncConversationComposerSendButtonByDraft === "function") {
          syncConversationComposerSendButtonByDraft(key);
        }
      }
    }

    function conversationReplyPreviewText(text) {
      const src = String(text || "").replace(/\r\n?/g, "\n").trim();
      if (!src) return "(空内容)";
      const lineLimited = src
        .split("\n")
        .slice(0, CONV_REPLY_PREVIEW_MAX_LINES)
        .join("\n");
      if (lineLimited.length <= CONV_REPLY_PREVIEW_MAX_CHARS) return lineLimited;
      return lineLimited.slice(0, CONV_REPLY_PREVIEW_MAX_CHARS) + "…";
    }

    function conversationReplyInjectedText(replyContext) {
      const ctx = normalizeConvReplyContext(replyContext);
      if (!ctx) return "";
      const title = "回复「" + String(ctx.timeLabel || "-") + " " + String(ctx.senderLabel || "我") + "」：";
      const quote = String(ctx.preview || "")
        .split("\n")
        .filter((line) => String(line || "").trim().length > 0)
        .map((line) => "> " + line)
        .join("\n");
      return title + "\n" + (quote || "> (空内容)") + "\n\n";
    }

    function stripReplyInjectedPrefixFromDraft(draftLike) {
      const d = (draftLike && typeof draftLike === "object") ? draftLike : null;
      if (!d) return false;
      const replyCtx = normalizeConvReplyContext(d.replyContext);
      if (!replyCtx) return false;
      const injectedText = String(replyCtx.injectedText || "").trim();
      if (!injectedText) return false;
      const currentText = String(d.text || "");
      if (!currentText.startsWith(injectedText)) return false;
      d.text = currentText.slice(injectedText.length).replace(/^\n+/, "");
      d.replyContext = Object.assign({}, replyCtx, { injectedText: "" });
      return true;
    }

    function renderConvComposerReplyContextByKey(key) {
      const { replyContainer } = convComposerUiElements();
      if (!replyContainer) return;
      const draft = getConvComposerDraftByKey(key);
      const ctx = normalizeConvReplyContext(draft.replyContext);
      replyContainer.innerHTML = "";
      if (!ctx) {
        replyContainer.style.display = "none";
        return;
      }
      const main = el("div", { class: "convreply-main" });
      const title = el("div", { class: "convreply-title", text: "↩ 正在回复 · " + String(ctx.senderLabel || "我") + (ctx.timeLabel ? (" · " + ctx.timeLabel) : "") });
      const preview = el("div", { class: "convreply-preview", text: String(ctx.preview || "(空内容)") });
      main.appendChild(title);
      main.appendChild(preview);
      const cancelBtn = el("button", { class: "btn textbtn convreply-cancel", type: "button", text: "取消回复" });
      cancelBtn.addEventListener("click", () => {
        clearConvComposerReplyContextByKey(String(key || ""), { removeInjectedText: true, focus: true });
      });
      replyContainer.appendChild(main);
      replyContainer.appendChild(cancelBtn);
      replyContainer.style.display = "flex";
    }

    function clearConvComposerReplyContextByKey(key, opts = {}) {
      const draftKey = String(key || "").trim();
      if (!draftKey) return;
      const removeInjectedText = Object.prototype.hasOwnProperty.call(opts, "removeInjectedText")
        ? !!opts.removeInjectedText
        : true;
      updateConvComposerDraftByKey(draftKey, (d) => {
        const prev = normalizeConvReplyContext(d.replyContext);
        if (prev && removeInjectedText) {
          const injectedText = String(prev.injectedText || "");
          if (injectedText && String(d.text || "").startsWith(injectedText)) {
            d.text = String(d.text || "").slice(injectedText.length).replace(/^\n+/, "");
          }
        }
        d.replyContext = null;
      });
      if (String(PCONV.composerBoundDraftKey || "") === draftKey) {
        applyConvComposerDraftToUiByKey(draftKey, { focus: !!opts.focus });
      }
    }

    function setConvComposerReplyByKey(key, payload) {
      const draftKey = String(key || "").trim();
      if (!draftKey) return false;
      const preview = conversationReplyPreviewText(payload && payload.text);
      const nextCtx = normalizeConvReplyContext({
        runId: String((payload && payload.runId) || "").trim(),
        bubbleKey: String((payload && payload.bubbleKey) || "").trim(),
        senderLabel: String((payload && payload.senderLabel) || "我").trim() || "我",
        timeLabel: String((payload && payload.timeLabel) || "").trim(),
        preview,
        createdAt: String((payload && payload.createdAt) || "").trim() || new Date().toISOString(),
      });
      if (!nextCtx) return false;
      updateConvComposerDraftByKey(draftKey, (d) => {
        stripReplyInjectedPrefixFromDraft(d);
        d.replyContext = nextCtx;
      });
      if (String(PCONV.composerBoundDraftKey || "") === draftKey) {
        applyConvComposerDraftToUiByKey(draftKey, { focus: true });
      }
      return true;
    }

    function getConvComposerAttachmentsForCurrentSession() {
      const key = currentConvComposerDraftKey();
      if (!key) return [];
      const d = ensureConvComposerDraftByKey(key);
      return Array.isArray(d.attachments) ? d.attachments : [];
    }

    function appendConvComposerAttachmentByKey(key, attachment) {
      const normalized = cloneConvComposerAttachment(attachment);
      if (!normalized) return;
      updateConvComposerDraftByKey(key, (d) => {
        d.attachments.push(normalized);
      });
      if (String(PCONV.composerBoundDraftKey || "") === String(key || "")) renderAttachments();
    }

    function clearConvComposerDraftByKey(key) {
      const k = String(key || "").trim();
      if (!k) return;
      updateConvComposerDraftByKey(k, (d) => {
        d.text = "";
        d.attachments = [];
        d.mentions = [];
        d.replyContext = null;
      });
      if (String(PCONV.composerBoundDraftKey || "") === k) {
        applyConvComposerDraftToUiByKey(k);
      }
    }

    function getConversationMemoStateByKey(key) {
      const k = String(key || "").trim();
      if (!k) return { count: 0, items: [], updatedAt: "", fetchedAt: 0 };
      const hit = PCONV.memoBySessionKey[k];
      if (hit && typeof hit === "object") return hit;
      const next = { count: 0, items: [], updatedAt: "", fetchedAt: 0 };
      PCONV.memoBySessionKey[k] = next;
      return next;
    }

    function getConversationMemoSelectedMapByKey(key) {
      const k = String(key || "").trim();
      if (!k) return Object.create(null);
      const hit = PCONV.memoSelectedBySessionKey[k];
      if (hit && typeof hit === "object") return hit;
      const next = Object.create(null);
      PCONV.memoSelectedBySessionKey[k] = next;
      return next;
    }

    function setConversationMemoHintByKey(key, text) {
      const k = String(key || "").trim();
      if (!k) return;
      PCONV.memoHintBySessionKey[k] = String(text || "").trim();
    }

    function memoCountText(n) {
      const count = Math.max(0, Number(n || 0));
      return count > 99 ? "99+" : String(count);
    }

    function conversationMemoSummary(session) {
      const current = (session && typeof session === "object") ? session : null;
      if (!current) return null;
      const topLevel = (current.memo_summary && typeof current.memo_summary === "object")
        ? current.memo_summary
        : ((current.memoSummary && typeof current.memoSummary === "object") ? current.memoSummary : null);
      if (topLevel) return topLevel;
      const metrics = (current.conversation_list_metrics && typeof current.conversation_list_metrics === "object")
        ? current.conversation_list_metrics
        : ((current.conversationListMetrics && typeof current.conversationListMetrics === "object")
          ? current.conversationListMetrics
          : null);
      if (!metrics) return null;
      return (metrics.memo_summary && typeof metrics.memo_summary === "object")
        ? metrics.memo_summary
        : ((metrics.memoSummary && typeof metrics.memoSummary === "object") ? metrics.memoSummary : null);
    }

    function conversationMemoSummaryCount(session) {
      const summary = conversationMemoSummary(session);
      if (!summary) return 0;
      const raw = Number(summary.memo_count || summary.memoCount || summary.count || 0);
      return Math.max(0, raw);
    }

    function resolveConversationMemoDisplayCount(session, key, state) {
      const totalCount = conversationMemoSummaryCount(session);
      if (totalCount > 0) return totalCount;
      return Math.max(0, countUnreadConversationMemosByKey(key, state));
    }

    function conversationMemoCountTitle(session, key, state) {
      const unreadCount = Math.max(0, countUnreadConversationMemosByKey(key, state));
      const totalCount = conversationMemoSummaryCount(session);
      if (totalCount > 0) {
        return unreadCount > 0
          ? ("备忘共 " + totalCount + " 条，未消费 " + unreadCount + " 条")
          : ("备忘共 " + totalCount + " 条");
      }
      return unreadCount > 0 ? ("备忘未消费：" + unreadCount) : "";
    }

    function getConversationUnreadCursorByKey(key) {
      const k = String(key || "").trim();
      if (!k) return "";
      return String(PCONV.unreadCursorBySessionKey[k] || "").trim();
    }

    function setConversationUnreadCursorByKey(key, createdAt) {
      const k = String(key || "").trim();
      if (!k) return;
      const ts = String(createdAt || "").trim();
      const prevTs = String(PCONV.unreadCursorBySessionKey[k] || "").trim();
      if (isUnreadMonotonicEnabled() && ts && prevTs) {
        const nextNum = toTimeNum(ts);
        const prevNum = toTimeNum(prevTs);
        if (nextNum >= 0 && prevNum >= 0 && nextNum < prevNum) {
          return;
        }
      }
      if (!ts) delete PCONV.unreadCursorBySessionKey[k];
      else PCONV.unreadCursorBySessionKey[k] = ts;
      persistSessionScopedMap(CONV_UNREAD_CURSOR_KEY, PCONV.unreadCursorBySessionKey);
    }

    function getConversationMemoConsumedMapByKey(key) {
      const k = String(key || "").trim();
      if (!k) return Object.create(null);
      const hit = PCONV.memoConsumedBySessionKey[k];
      if (hit && typeof hit === "object") return hit;
      const next = Object.create(null);
      PCONV.memoConsumedBySessionKey[k] = next;
      return next;
    }

    function persistConversationMemoConsumedMap() {
      persistSessionScopedMap(CONV_MEMO_CONSUMED_KEY, PCONV.memoConsumedBySessionKey);
    }

    function cleanConversationMemoConsumedByKey(key, items) {
      const k = String(key || "").trim();
      if (!k) return;
      const consumed = getConversationMemoConsumedMapByKey(k);
      const valid = new Set((Array.isArray(items) ? items : []).map((it) => String((it && it.id) || "").trim()).filter(Boolean));
      let changed = false;
      Object.keys(consumed).forEach((memoId) => {
        if (!valid.has(memoId)) {
          delete consumed[memoId];
          changed = true;
        }
      });
      if (changed) persistConversationMemoConsumedMap();
    }

    function markConversationMemosConsumedByKey(key, ids) {
      const k = String(key || "").trim();
      if (!k) return;
      const consumed = getConversationMemoConsumedMapByKey(k);
      let changed = false;
      (Array.isArray(ids) ? ids : []).forEach((id) => {
        const memoId = String(id || "").trim();
        if (!memoId || consumed[memoId]) return;
        consumed[memoId] = true;
        changed = true;
      });
      if (changed) persistConversationMemoConsumedMap();
    }

    function countUnreadConversationMemosByKey(key, state) {
      const k = String(key || "").trim();
      if (!k) return 0;
      const st = (state && typeof state === "object") ? state : getConversationMemoStateByKey(k);
      const items = Array.isArray(st.items) ? st.items : [];
      if (!items.length) return Math.max(0, Number(st.count || 0));
      const consumed = getConversationMemoConsumedMapByKey(k);
      let unread = 0;
      for (const it of items) {
        const memoId = String((it && it.id) || "").trim();
        if (!memoId || consumed[memoId]) continue;
        unread += 1;
      }
      return unread;
    }

    function resolveConversationRunsBySessionKey(sessionKey, sessionId) {
      const key = String(sessionKey || "").trim();
      if (key && Array.isArray(PCONV.sessionTimelineMap[key])) return PCONV.sessionTimelineMap[key];
      const sid = String(sessionId || "").trim();
      if (sid && Array.isArray(PCONV.runsBySession[sid])) return PCONV.runsBySession[sid];
      return [];
    }

    function injectConversationAckRunToTimeline(ctx = {}, optimistic = {}, response = {}, opts = {}) {
      const context = (ctx && typeof ctx === "object") ? ctx : {};
      const projectId = String(context.projectId || context.project_id || STATE.project || "").trim();
      const sessionId = String(context.sessionId || context.session_id || "").trim();
      const run = (response && response.run && typeof response.run === "object") ? response.run : {};
      const runId = String(run.id || run.run_id || run.runId || "").trim();
      if (!projectId || !sessionId || !runId) return null;
      if (!PCONV.runsBySession || typeof PCONV.runsBySession !== "object") {
        PCONV.runsBySession = Object.create(null);
      }
      if (!PCONV.sessionTimelineMap || typeof PCONV.sessionTimelineMap !== "object") {
        PCONV.sessionTimelineMap = Object.create(null);
      }
      const optimisticPayload = (optimistic && typeof optimistic === "object") ? optimistic : {};
      const createdAt = String(
        run.createdAt
        || run.created_at
        || optimisticPayload.createdAt
        || optimisticPayload.created_at
        || (typeof conversationStoreNowIso === "function" ? conversationStoreNowIso() : new Date().toISOString())
      ).trim();
      const messagePreview = String(firstNonEmptyText([
        run.messagePreview,
        run.preview,
        optimisticPayload.message,
        optimisticPayload.text,
      ]) || "").trim();
      const normalizedRun = {
        ...run,
        id: runId,
        project_id: projectId,
        session_id: sessionId,
        channel_name: String(context.channelName || context.channel_name || "").trim(),
        cli_type: String(context.cliType || context.cli_type || "codex").trim() || "codex",
        status: normalizeDisplayState(run.status || run.display_state || run.displayState || "queued", "queued"),
        createdAt,
        created_at: createdAt,
        updatedAt: String(run.updatedAt || run.updated_at || createdAt).trim(),
        updated_at: String(run.updatedAt || run.updated_at || createdAt).trim(),
        messagePreview,
        preview: String(run.preview || messagePreview).trim(),
        client_message_id: String(run.client_message_id || run.clientMessageId || optimisticPayload.clientMessageId || optimisticPayload.client_message_id || "").trim(),
        attachments: Array.isArray(optimisticPayload.attachments) ? optimisticPayload.attachments.map((item) => ({ ...(item || {}) })) : [],
      };
      const timelineKey = projectId + "::" + sessionId;
      const existingRuns = Array.isArray(PCONV.sessionTimelineMap[timelineKey])
        ? PCONV.sessionTimelineMap[timelineKey]
        : (Array.isArray(PCONV.runsBySession[sessionId]) ? PCONV.runsBySession[sessionId] : []);
      const mergedRuns = typeof mergeRunsById === "function"
        ? mergeRunsById(existingRuns, [normalizedRun])
        : [normalizedRun].concat((Array.isArray(existingRuns) ? existingRuns : []).filter((item) => String((item && item.id) || "").trim() !== runId));
      PCONV.sessionTimelineMap[timelineKey] = mergedRuns;
      PCONV.runsBySession[sessionId] = mergedRuns;
      if (typeof conversationStoreUpsertRun === "function") {
        conversationStoreUpsertRun(projectId, sessionId, normalizedRun, {
          ...(opts && typeof opts === "object" ? opts : {}),
          source: String(((opts && opts.source) || "announce-ack")).trim() || "announce-ack",
        });
      }
      return normalizedRun;
    }

    function isUnreadTerminalRun(run) {
      const rid = String((run && run.id) || "").trim();
      const detail = rid ? (PCONV.detailMap[rid] || null) : null;
      const st = getRunDisplayState(run, detail);
      if (!st) return false;
      return !isRunWorking(st);
    }

    function latestUnreadTerminalCreatedAt(runs) {
      const src = Array.isArray(runs) ? runs : [];
      let latestTs = -1;
      let latestText = "";
      for (const r of src) {
        if (!isUnreadTerminalRun(r)) continue;
        const createdAt = String((r && r.createdAt) || "").trim();
        const t = toTimeNum(createdAt);
        if (t >= 0 && t > latestTs) {
          latestTs = t;
          latestText = createdAt;
        }
      }
      if (latestText) return latestText;
      for (const r of src) {
        if (!isUnreadTerminalRun(r)) continue;
        const createdAt = String((r && r.createdAt) || "").trim();
        if (createdAt && (!latestText || createdAt > latestText)) latestText = createdAt;
      }
      return latestText;
    }

    function latestUnreadTerminalCreatedAtFromSession(sessionId) {
      const sid = String(sessionId || "").trim();
      if (!sid) return "";
      const sessions = Array.isArray(PCONV.sessions) ? PCONV.sessions : [];
      const session = sessions.find((it) => String((it && (it.sessionId || it.id)) || "").trim() === sid) || null;
      if (!session) return "";
      const latestRunSummary = getSessionLatestRunSummary(session);
      if (!isLatestRunSummaryTerminal(latestRunSummary)) return "";
      return String(latestRunSummary.updated_at || "").trim();
    }

    function countUnreadConversationMessagesByKey(sessionKey, sessionId) {
      const key = String(sessionKey || "").trim();
      if (!key) return 0;
      const cursorTs = toTimeNum(getConversationUnreadCursorByKey(key));
      const src = resolveConversationRunsBySessionKey(key, sessionId);
      if (!src.length) {
        const latestCreatedAt = latestUnreadTerminalCreatedAtFromSession(sessionId);
        if (!latestCreatedAt) return 0;
        const latestTs = toTimeNum(latestCreatedAt);
        if (cursorTs >= 0 && latestTs >= 0) return latestTs > cursorTs ? 1 : 0;
        return 1;
      }
      let unread = 0;
      for (const r of src) {
        if (!isUnreadTerminalRun(r)) continue;
        const createdAt = String((r && r.createdAt) || "").trim();
        if (!createdAt) continue;
        const ts = toTimeNum(createdAt);
        if (cursorTs >= 0 && ts >= 0) {
          if (ts > cursorTs) unread += 1;
          continue;
        }
        if (cursorTs < 0) unread += 1;
      }
      return unread;
    }

    function ensureConversationUnreadCursorSeededByKey(sessionKey, sessionId) {
      const key = String(sessionKey || "").trim();
      if (!key) return false;
      const hasCursor = Object.prototype.hasOwnProperty.call(PCONV.unreadCursorBySessionKey, key);
      if (hasCursor) return false;
      const seedRuns = resolveConversationRunsBySessionKey(key, sessionId);
      const seedTs = latestUnreadTerminalCreatedAt(seedRuns) || latestUnreadTerminalCreatedAtFromSession(sessionId);
      if (!seedTs) return false;
      setConversationUnreadCursorByKey(key, seedTs);
      return true;
    }

    function seedConversationUnreadCursorsForSessions(projectId, sessions) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return false;
      let changed = false;
      const rows = Array.isArray(sessions) ? sessions : [];
      for (const s of rows) {
        const sid = String((s && (s.sessionId || s.id)) || "").trim();
        if (!sid) continue;
        const key = convComposerDraftKey(pid, sid);
        if (!key) continue;
        if (ensureConversationUnreadCursorSeededByKey(key, sid)) changed = true;
      }
      return changed;
    }

    function consumeConversationUnreadByCtx(ctx) {
      if (!ctx || !ctx.projectId || !ctx.sessionId) return false;
      const key = convComposerDraftKey(ctx.projectId, ctx.sessionId);
      if (!key) return false;
      ensureConversationUnreadCursorSeededByKey(key, ctx.sessionId);
      const runs = resolveConversationRunsBySessionKey(key, ctx.sessionId);
      const latestCreatedAt = latestUnreadTerminalCreatedAt(runs) || latestUnreadTerminalCreatedAtFromSession(ctx.sessionId);
      if (!latestCreatedAt) return false;
      const prev = getConversationUnreadCursorByKey(key);
      if (prev === latestCreatedAt) return false;
      setConversationUnreadCursorByKey(key, latestCreatedAt);
      return true;
    }

    function refreshConversationCountDots() {
      if (STATE.panelMode === "conv") {
        if (isConversationListScrollActive()) {
          queueDeferredConversationRender({ panelRender: true });
          return;
        }
        buildConversationLeftList();
        buildConversationMainList(document.getElementById("fileList"));
        return;
      }
      if (STATE.panelMode === "channel") {
        buildChannelConversationList();
      }
    }

    function normalizeConversationMemoAttachment(raw) {
      if (!raw || typeof raw !== "object") return null;
      const src = String(raw.url || raw.dataUrl || "").trim();
      const filename = String(raw.filename || "").trim();
      const originalName = String(raw.originalName || raw.filename || "").trim();
      if (!src && !filename) return null;
      return {
        filename,
        originalName: originalName || filename || "attachment",
        url: src,
        dataUrl: src || "",
      };
    }

    function normalizeConversationMemoItem(raw) {
      if (!raw || typeof raw !== "object") return null;
      const id = String(raw.id || "").trim();
      if (!id) return null;
      const text = String(raw.text || raw.message || "").trim();
      const attachments = (Array.isArray(raw.attachments) ? raw.attachments : [])
        .map(normalizeConversationMemoAttachment)
        .filter(Boolean);
      return {
        id,
        text,
        attachments,
        createdAt: String(raw.createdAt || "").trim(),
        updatedAt: String(raw.updatedAt || raw.createdAt || "").trim(),
      };
    }

    async function loadConversationMemos(projectId, sessionId) {
      const qs = new URLSearchParams();
      qs.set("projectId", String(projectId || "").trim());
      qs.set("sessionId", String(sessionId || "").trim());
      const r = await fetch("/api/conversation-memos?" + qs.toString(), { cache: "no-store" });
      if (!r.ok) throw new Error((await parseResponseDetail(r)) || ("HTTP " + r.status));
      return await r.json();
    }

    async function createConversationMemo(payload) {
      const r = await fetch("/api/conversation-memos", {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload || {}),
      });
      if (!r.ok) throw new Error((await parseResponseDetail(r)) || ("HTTP " + r.status));
      return await r.json();
    }

    async function deleteConversationMemos(payload) {
      const r = await fetch("/api/conversation-memos/delete", {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload || {}),
      });
      if (!r.ok) throw new Error((await parseResponseDetail(r)) || ("HTTP " + r.status));
      return await r.json();
    }

    async function clearConversationMemos(payload) {
      const r = await fetch("/api/conversation-memos/clear", {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload || {}),
      });
      if (!r.ok) throw new Error((await parseResponseDetail(r)) || ("HTTP " + r.status));
      return await r.json();
    }

    async function ensureConversationMemosLoaded(projectId, sessionId, opts = {}) {
      const key = convComposerDraftKey(projectId, sessionId);
      if (!key) return;
      if (!PCONV.memoPromiseBySessionKey || typeof PCONV.memoPromiseBySessionKey !== "object") {
        PCONV.memoPromiseBySessionKey = Object.create(null);
      }
      const force = !!opts.force;
      const maxAgeMs = Math.max(1000, Number(opts.maxAgeMs || 15_000));
      const source = String((opts && opts.source) || "").trim().toLowerCase();
      if (!force && !isConversationMemoDrawerOpenForKey(key) && source !== "memo-drawer") return;
      const cur = getConversationMemoStateByKey(key);
      const fetchedAt = Number(cur.fetchedAt || 0);
      const stale = !fetchedAt || (Date.now() - fetchedAt > maxAgeMs);
      if (!force && !stale) return;
      if (!force && PCONV.memoPromiseBySessionKey[key]) return PCONV.memoPromiseBySessionKey[key];

      const seq = Number(PCONV.memoRequestSeqBySessionKey[key] || 0) + 1;
      PCONV.memoRequestSeqBySessionKey[key] = seq;
      PCONV.memoLoadingBySessionKey[key] = true;
      renderConversationMemoUi();
      PCONV.memoPromiseBySessionKey[key] = (async () => {
        try {
        const payload = await loadConversationMemos(projectId, sessionId);
        if (Number(PCONV.memoRequestSeqBySessionKey[key] || 0) !== seq) return;
        const items = (Array.isArray(payload && payload.items) ? payload.items : [])
          .map(normalizeConversationMemoItem)
          .filter(Boolean);
        const countRaw = Number((payload && payload.count) || items.length || 0);
        const next = {
          count: Math.max(items.length, countRaw),
          items,
          updatedAt: String((payload && payload.updatedAt) || "").trim(),
          fetchedAt: Date.now(),
        };
        PCONV.memoBySessionKey[key] = next;
        cleanConversationMemoConsumedByKey(key, items);
        } catch (e) {
        if (Number(PCONV.memoRequestSeqBySessionKey[key] || 0) !== seq) return;
        setConversationMemoHintByKey(key, "备忘加载失败：" + String((e && e.message) || e || "未知错误"));
        } finally {
        if (Number(PCONV.memoRequestSeqBySessionKey[key] || 0) === seq) {
          PCONV.memoLoadingBySessionKey[key] = false;
        }
        delete PCONV.memoPromiseBySessionKey[key];
        renderConversationMemoUi();
        }
      })();
      return PCONV.memoPromiseBySessionKey[key];
    }

    function isConversationMemoDrawerOpenForKey(key) {
      const targetKey = String(key || "").trim();
      if (!targetKey) return false;
      return !!(PCONV.memoDrawerOpen && String(PCONV.memoDrawerSessionKey || "").trim() === targetKey);
    }

    function hideConversationMemoEntry() {
      const btn = document.getElementById("detailMemoBtn");
      const dot = document.getElementById("detailMemoCountDot");
      if (btn) {
        btn.style.display = "none";
        btn.onclick = null;
      }
      if (dot) dot.style.display = "none";
      if (PCONV.memoDrawerOpen) {
        PCONV.memoDrawerOpen = false;
        PCONV.memoDrawerSessionKey = "";
        renderConversationMemoDrawer();
      }
    }

    function renderConversationMemoEntry(ctx) {
      const btn = document.getElementById("detailMemoBtn");
      const dot = document.getElementById("detailMemoCountDot");
      if (!btn || !dot) return;
      if (!ctx || !ctx.projectId || !ctx.sessionId) {
        hideConversationMemoEntry();
        return;
      }
      const key = convComposerDraftKey(ctx.projectId, ctx.sessionId);
      btn.style.display = "";
      const state = getConversationMemoStateByKey(key);
      const session = (typeof findConversationSessionById === "function")
        ? findConversationSessionById(String(ctx.sessionId || "").trim())
        : null;
      const count = resolveConversationMemoDisplayCount(session, key, state);
      const memoTitle = conversationMemoCountTitle(session, key, state);
      btn.title = memoTitle ? ("会话需求暂存与备忘 · " + memoTitle) : "会话需求暂存与备忘";
      if (count > 0) {
        dot.style.display = "inline-flex";
        dot.textContent = memoCountText(count);
        dot.title = memoTitle;
      } else {
        dot.style.display = "none";
        dot.title = "";
      }
      btn.onclick = () => {
        const same = PCONV.memoDrawerOpen && String(PCONV.memoDrawerSessionKey || "") === key;
        if (same) {
          PCONV.memoDrawerOpen = false;
          renderConversationMemoDrawer();
          return;
        }
        PCONV.taskDrawerOpen = false;
        if (typeof closeConversationTaskDetailViewer === "function") closeConversationTaskDetailViewer();
        if (typeof renderConversationTaskDrawer === "function") renderConversationTaskDrawer();
        if (typeof currentConversationTaskPayload === "function" && typeof renderConversationTaskEntry === "function") {
          const taskPayload = currentConversationTaskPayload();
          renderConversationTaskEntry(taskPayload.ctx, taskPayload);
        }
        PCONV.memoDrawerOpen = true;
        PCONV.memoDrawerSessionKey = key;
        renderConversationMemoDrawer();
        ensureConversationMemosLoaded(ctx.projectId, ctx.sessionId, { maxAgeMs: 6000 });
      };
    }

    function mergeMemoAttachments(existing, incoming) {
      const out = [];
      const seen = new Set();
      const push = (att) => {
        const norm = normalizeConversationMemoAttachment(att) || cloneConvComposerAttachment(att);
        if (!norm) return;
        const dedupeKey = [
          String(norm.filename || "").trim(),
          String(norm.url || norm.dataUrl || "").trim(),
          String(norm.originalName || "").trim(),
        ].join("|");
        if (seen.has(dedupeKey)) return;
        seen.add(dedupeKey);
        out.push({
          filename: String(norm.filename || ""),
          originalName: String(norm.originalName || norm.filename || "attachment"),
          url: String(norm.url || norm.dataUrl || ""),
          dataUrl: String(norm.dataUrl || norm.url || ""),
        });
      };
      (Array.isArray(existing) ? existing : []).forEach(push);
      (Array.isArray(incoming) ? incoming : []).forEach(push);
      return out;
    }

    function renderConversationMemoDrawer() {
      const mask = document.getElementById("convMemoDrawerMask");
      const list = document.getElementById("convMemoList");
      const sub = document.getElementById("convMemoDrawerSub");
      const hint = document.getElementById("convMemoHint");
      const selectAllBtn = document.getElementById("convMemoSelectAllBtn");
      const applyBtn = document.getElementById("convMemoApplyBtn");
      const applyDeleteBtn = document.getElementById("convMemoApplyDeleteBtn");
      const sendDeleteBtn = document.getElementById("convMemoSendDeleteBtn");
      const deleteBtn = document.getElementById("convMemoDeleteBtn");
      const clearBtn = document.getElementById("convMemoClearBtn");
      if (!mask || !list || !sub || !hint || !selectAllBtn || !applyBtn || !applyDeleteBtn || !sendDeleteBtn || !deleteBtn || !clearBtn) return;
      if (!PCONV.memoDrawerOpen) {
        mask.classList.remove("show");
        return;
      }
      mask.classList.add("show");
      const key = String(PCONV.memoDrawerSessionKey || currentConvComposerDraftKey() || "").trim();
      if (!key) return;
      PCONV.memoDrawerSessionKey = key;
      const state = getConversationMemoStateByKey(key);
      const items = Array.isArray(state.items) ? state.items : [];
      const selectedMap = getConversationMemoSelectedMapByKey(key);
      const selectedIds = items.filter((it) => selectedMap[it.id]).map((it) => it.id);
      const unreadCount = countUnreadConversationMemosByKey(key, state);
      const loading = !!PCONV.memoLoadingBySessionKey[key];
      const busyAction = String(PCONV.memoActionBusyBySessionKey[key] || "");
      const memoHint = String(PCONV.memoHintBySessionKey[key] || "").trim();
      const currentCtx = currentConversationCtx();
      const channelName = currentCtx ? String(currentCtx.channelName || currentCtx.alias || "当前会话") : "当前会话";
      const total = Math.max(0, Number(state.count || items.length || 0));
      sub.textContent = channelName + " · 未消费 " + unreadCount + " / 共 " + total + " 条";
      hint.textContent = memoHint || "将当前输入区内容点击“记录”后可在这里管理。";
      list.innerHTML = "";
      if (loading) {
        list.appendChild(el("div", { class: "memo-empty", text: "备忘加载中..." }));
      } else if (!items.length) {
        list.appendChild(el("div", { class: "memo-empty", text: "当前会话暂无备忘记录。" }));
      } else {
        for (const item of items) {
          const row = el("div", { class: "memo-item" });
          const head = el("div", { class: "memo-item-head" });
          const ckWrap = el("label", { class: "memo-item-check" });
          const ck = document.createElement("input");
          ck.type = "checkbox";
          ck.checked = !!selectedMap[item.id];
          ck.addEventListener("change", () => {
            if (ck.checked) selectedMap[item.id] = true;
            else delete selectedMap[item.id];
            renderConversationMemoDrawer();
          });
          ckWrap.appendChild(ck);
          ckWrap.appendChild(el("span", { text: item.text ? "含文本" : "仅附件" }));
          head.appendChild(ckWrap);
          const ts = compactDateTime(item.updatedAt || item.createdAt || "") || "-";
          head.appendChild(el("span", { text: ts }));
          row.appendChild(head);
          row.appendChild(el("div", { class: "memo-item-text", text: item.text || "(空文本)" }));
          if (Array.isArray(item.attachments) && item.attachments.length) {
            const files = el("div", { class: "memo-item-files" });
            item.attachments.forEach((att, idx) => {
              const name = String(att.originalName || att.filename || ("图片" + (idx + 1)));
              const safeName = name.replace(/^图片(\d+)$/, "附件$1");
              files.appendChild(el("span", { class: "memo-file-chip", text: safeName }));
            });
            row.appendChild(files);
          }
          const rowOps = el("div", { class: "memo-item-row" });
          const quickBtn = el("button", { class: "btn", text: "单条放入" });
          quickBtn.disabled = !!busyAction;
          quickBtn.addEventListener("click", () => {
            selectedMap[item.id] = true;
            applyConversationMemosToComposer([item], key);
          });
          rowOps.appendChild(quickBtn);
          const quickApplyDeleteBtn = el("button", { class: "btn danger", text: "单条放入并删除" });
          quickApplyDeleteBtn.disabled = !!busyAction;
          quickApplyDeleteBtn.addEventListener("click", () => {
            applyAndDeleteConversationMemosByRows(key, [item]);
          });
          rowOps.appendChild(quickApplyDeleteBtn);
          const quickSendDeleteBtn = el("button", { class: "btn primary", text: "单条发送并删除" });
          quickSendDeleteBtn.disabled = !!busyAction;
          quickSendDeleteBtn.addEventListener("click", () => {
            sendAndDeleteConversationMemosByRows(key, [item]);
          });
          rowOps.appendChild(quickSendDeleteBtn);
          row.appendChild(rowOps);
          list.appendChild(row);
        }
      }
      selectAllBtn.disabled = !!busyAction || loading || !items.length;
      selectAllBtn.textContent = selectedIds.length === items.length && items.length ? "取消全选" : "全选";
      applyBtn.disabled = !!busyAction || loading || selectedIds.length <= 0;
      applyDeleteBtn.disabled = !!busyAction || loading || selectedIds.length <= 0;
      sendDeleteBtn.disabled = !!busyAction || loading || selectedIds.length <= 0;
      deleteBtn.disabled = !!busyAction || loading || selectedIds.length <= 0;
      clearBtn.disabled = !!busyAction || loading || !items.length;
      if (busyAction === "save") applyBtn.textContent = "处理中...";
      else applyBtn.textContent = "放入";
      if (busyAction === "apply-delete") applyDeleteBtn.textContent = "处理中...";
      else applyDeleteBtn.textContent = "放入删";
      if (busyAction === "send-delete") sendDeleteBtn.textContent = "发送中...";
      else sendDeleteBtn.textContent = "发并删";
      if (busyAction === "delete") deleteBtn.textContent = "删除中...";
      else deleteBtn.textContent = "删选中";
      if (busyAction === "clear") clearBtn.textContent = "清空中...";
      else clearBtn.textContent = "清空";
    }

    function renderConversationMemoUi() {
      const ctx = currentConversationCtx();
      if (ctx) {
        renderConversationMemoEntry(ctx);
      }
      else hideConversationMemoEntry();
      renderConversationMemoDrawer();
      refreshConversationCountDots();
    }

    function getConversationFileStateByKey(key) {
      const rawKey = String(key || "").trim();
      const state = rawKey ? PCONV.filesBySessionKey[rawKey] : null;
      if (state && typeof state === "object") return state;
      return { count: 0, items: [], updatedAt: "", fetchedAt: 0 };
    }

    function getConversationFileStarredMapByKey(key) {
      const rawKey = String(key || "").trim();
      if (!rawKey) return Object.create(null);
      const current = PCONV.fileStarredBySessionKey[rawKey];
      if (current && typeof current === "object") return current;
      const next = Object.create(null);
      PCONV.fileStarredBySessionKey[rawKey] = next;
      return next;
    }

    function persistConversationFileStarredMap() {
      persistSessionScopedMap(CONV_FILE_STARRED_KEY, PCONV.fileStarredBySessionKey);
    }

    function hideConversationFileEntry() {
      const btn = document.getElementById("detailFilesBtn");
      const total = document.getElementById("detailFilesCountTotal");
      const starWrap = document.getElementById("detailFilesCountStarWrap");
      if (btn) {
        btn.style.display = "none";
        btn.classList.remove("active");
      }
      if (total) total.style.display = "none";
      if (starWrap) starWrap.style.display = "none";
    }

    function countConversationFilesText(count) {
      const num = Math.max(0, Number(count || 0));
      if (!num) return "0";
      if (num > 99) return "99+";
      return String(num);
    }

    function isCollectableConversationFileObject(obj) {
      if (!obj || typeof obj !== "object") return false;
      const kind = String(obj.kind || "").trim().toLowerCase();
      const tone = String(obj.tone || "").trim().toLowerCase();
      if (kind === "attachment_url" || kind === "attachment_path") return true;
      if (kind === "share_path" || kind === "share_url") return true;
      if (kind === "fs_path") return true;
      if (kind === "url") return false;
      return tone === "file" || tone === "dir" || tone === "attach";
    }

    function buildConversationFileObjectKey(obj) {
      if (!obj || typeof obj !== "object") return "";
      const path = String(obj.path || "").trim();
      if (path) return "path:" + path;
      const openUrl = String(obj.openUrl || "").trim();
      if (openUrl) return "url:" + openUrl;
      const value = String(obj.value || obj.label || "").trim();
      if (value) return "value:" + value;
      return "";
    }

    function conversationFileTitleFromObject(obj) {
      if (!obj || typeof obj !== "object") return "未命名文件";
      const path = String(obj.path || "").trim();
      const value = String(obj.value || "").trim();
      const openUrl = String(obj.openUrl || "").trim();
      const candidates = [path, value, openUrl, String(obj.label || "").trim()].filter(Boolean);
      for (const one of candidates) {
        const cleaned = one.replace(/[?#].*$/, "").replace(/\/+$/, "");
        const parts = cleaned.split(/[\\/]/).filter(Boolean);
        const tail = parts.length ? parts[parts.length - 1] : cleaned;
        if (tail) return tail;
      }
      return "未命名文件";
    }

    function conversationFileTypeLabel(obj) {
      const raw = obj && typeof obj === "object" ? obj : {};
      const kind = String(raw.kind || "").trim().toLowerCase();
      const tone = String(raw.tone || "").trim().toLowerCase();
      if (kind === "attachment_url" || kind === "attachment_path" || tone === "attach") return "附件";
      if (kind === "share_path" || kind === "share_url") return "分享页";
      if (kind === "fs_path" && tone === "dir") return "目录";
      if (tone === "dir") return "目录";
      return "文件";
    }

    function getConversationFileSortByKey(key) {
      const rawKey = String(key || "").trim();
      if (!rawKey) return "time_desc";
      const raw = String(PCONV.fileSortBySessionKey[rawKey] || "").trim().toLowerCase();
      if (raw === "time_asc" || raw === "mention_desc" || raw === "name_asc") return raw;
      return "time_desc";
    }

    function setConversationFileSortByKey(key, value) {
      const rawKey = String(key || "").trim();
      if (!rawKey) return;
      PCONV.fileSortBySessionKey[rawKey] = String(value || "time_desc").trim().toLowerCase();
    }

    function conversationFileFilterOptions() {
      return [
        { value: "doc", label: "文档" },
        { value: "page", label: "页面" },
        { value: "pdf", label: "PDF" },
        { value: "image", label: "图片" },
        { value: "directory", label: "目录" },
        { value: "code", label: "代码" },
        { value: "data", label: "数据" },
        { value: "attach", label: "附件" },
        { value: "other", label: "其他" },
      ];
    }

    function defaultConversationFileFilterValues() {
      return ["doc", "page"];
    }

    function normalizeConversationFileFilterValues(values) {
      const allowed = new Set(conversationFileFilterOptions().map((it) => String(it.value || "").trim()));
      const out = [];
      const seen = new Set();
      (Array.isArray(values) ? values : []).forEach((raw) => {
        const value = String(raw || "").trim();
        if (!value || !allowed.has(value) || seen.has(value)) return;
        seen.add(value);
        out.push(value);
      });
      return out.length ? out : defaultConversationFileFilterValues().slice();
    }

    function getConversationFileTypeFilterByKey(key) {
      const rawKey = String(key || "").trim();
      if (!rawKey) return defaultConversationFileFilterValues().slice();
      const current = PCONV.fileTypeFilterBySessionKey[rawKey];
      const next = normalizeConversationFileFilterValues(Array.isArray(current) ? current : defaultConversationFileFilterValues());
      PCONV.fileTypeFilterBySessionKey[rawKey] = next.slice();
      return next;
    }

    function setConversationFileTypeFilterByKey(key, values) {
      const rawKey = String(key || "").trim();
      if (!rawKey) return;
      PCONV.fileTypeFilterBySessionKey[rawKey] = normalizeConversationFileFilterValues(values).slice();
    }

    function conversationFileFilterCategory(item) {
      const rawItem = item && typeof item === "object" ? item : {};
      const typeLabel = String(rawItem.typeLabel || "").trim();
      if (typeLabel === "目录") return "directory";
      const path = String(rawItem.path || rawItem.label || rawItem.title || rawItem.openUrl || "").trim().toLowerCase();
      const ext = (path.match(/\.([a-z0-9]+)(?:$|[?#])/i) || [null, ""])[1].toLowerCase();
      if (typeLabel === "分享页") return "page";
      if (ext === "md" || ext === "markdown" || ext === "txt" || ext === "doc" || ext === "docx") return "doc";
      if (ext === "html" || ext === "htm") return "page";
      if (ext === "pdf") return "pdf";
      if (ext === "png" || ext === "jpg" || ext === "jpeg" || ext === "gif" || ext === "webp" || ext === "svg" || ext === "bmp") return "image";
      if (ext === "js" || ext === "ts" || ext === "tsx" || ext === "jsx" || ext === "css" || ext === "scss" || ext === "less" || ext === "vue") return "code";
      if (ext === "json" || ext === "yml" || ext === "yaml" || ext === "toml" || ext === "csv" || ext === "tsv" || ext === "xml") return "data";
      if (typeLabel === "附件") return "attach";
      return "other";
    }

    function conversationFileFilterLabelMap() {
      const map = Object.create(null);
      conversationFileFilterOptions().forEach((it) => {
        map[String(it.value || "").trim()] = String(it.label || "").trim();
      });
      return map;
    }

    function renderConversationFileFilterBar(key, items) {
      const filterBar = document.getElementById("convFileTypeFilterBar");
      if (!filterBar) return;
      filterBar.innerHTML = "";
      const draftKey = String(key || "").trim();
      if (!draftKey) return;
      const options = conversationFileFilterOptions();
      const activeValues = getConversationFileTypeFilterByKey(draftKey);
      const activeSet = new Set(activeValues);
      const allValues = options.map((it) => String(it.value || "").trim()).filter(Boolean);
      const allActive = activeValues.length === allValues.length;
      const counts = Object.create(null);
      (Array.isArray(items) ? items : []).forEach((item) => {
        const category = conversationFileFilterCategory(item);
        counts[category] = Number(counts[category] || 0) + 1;
      });

      const allBtn = el("button", {
        class: "conv-file-filter-btn" + (allActive ? " active all-active" : ""),
        type: "button",
        text: "全部",
        title: allActive ? "当前已展示全部类型，再点一次恢复默认文档/页面筛选" : "展示全部文件类型",
      });
      allBtn.addEventListener("click", () => {
        setConversationFileTypeFilterByKey(draftKey, allActive ? defaultConversationFileFilterValues() : allValues);
        renderConversationFileDrawer();
      });
      filterBar.appendChild(allBtn);

      options.forEach((opt) => {
        const value = String(opt.value || "").trim();
        const count = Number(counts[value] || 0);
        const isActive = activeSet.has(value);
        const btn = el("button", {
          class: "conv-file-filter-btn" + (isActive ? " active" : ""),
          type: "button",
          text: String(opt.label || ""),
          title: count ? (String(opt.label || "") + " · " + count + " 个") : (String(opt.label || "") + " · 当前会话暂无此类型"),
        });
        if (!count) btn.disabled = true;
        btn.addEventListener("click", () => {
          if (!count) return;
          let next = activeValues.slice();
          if (isActive) {
            if (next.length <= 1) return;
            next = next.filter((it) => it !== value);
          } else {
            next.push(value);
          }
          setConversationFileTypeFilterByKey(draftKey, next);
          renderConversationFileDrawer();
        });
        filterBar.appendChild(btn);
      });
    }

    function conversationFileIconMeta(item) {
      const rawItem = item && typeof item === "object" ? item : {};
      const path = String(rawItem.path || rawItem.label || rawItem.title || "").trim().toLowerCase();
      const ext = (path.match(/\.([a-z0-9]+)(?:$|[?#])/i) || [null, ""])[1].toLowerCase();
      const typeLabel = String(rawItem.typeLabel || "").trim();
      if (typeLabel === "目录") return { glyph: "DIR", tone: "folder" };
      if (typeLabel === "分享页") return { glyph: "LINK", tone: "share" };
      if (typeLabel === "附件" && !ext) return { glyph: "ATT", tone: "attach" };
      if (ext === "js" || ext === "ts" || ext === "tsx" || ext === "jsx") return { glyph: "JS", tone: "code" };
      if (ext === "css" || ext === "scss" || ext === "less") return { glyph: "CSS", tone: "style" };
      if (ext === "html" || ext === "htm" || ext === "vue") return { glyph: "HTML", tone: "style" };
      if (ext === "json" || ext === "yml" || ext === "yaml" || ext === "toml") return { glyph: "DATA", tone: "data" };
      if (ext === "md" || ext === "txt" || ext === "doc" || ext === "docx") return { glyph: "DOC", tone: "doc" };
      if (ext === "png" || ext === "jpg" || ext === "jpeg" || ext === "gif" || ext === "webp" || ext === "svg") return { glyph: "IMG", tone: "image" };
      if (ext === "pdf") return { glyph: "PDF", tone: "pdf" };
      if (ext === "zip" || ext === "tar" || ext === "gz" || ext === "rar" || ext === "7z") return { glyph: "ZIP", tone: "archive" };
      if (typeLabel === "附件") return { glyph: "ATT", tone: "attach" };
      return { glyph: "FILE", tone: "file" };
    }

    function renderConversationFileEntry(ctx) {
      const btn = document.getElementById("detailFilesBtn");
      const total = document.getElementById("detailFilesCountTotal");
      const starWrap = document.getElementById("detailFilesCountStarWrap");
      const starCount = document.getElementById("detailFilesCountStar");
      if (!btn || !total || !starWrap || !starCount) return;
      if (!ctx || !ctx.projectId || !ctx.sessionId) {
        hideConversationFileEntry();
        return;
      }
      const key = convComposerDraftKey(ctx.projectId, ctx.sessionId);
      btn.style.display = "";
      const state = getConversationFileStateByKey(key);
      const count = Math.max(0, Number(state.count || (Array.isArray(state.items) ? state.items.length : 0) || 0));
      const starredMap = getConversationFileStarredMapByKey(key);
      const starred = Array.isArray(state.items)
        ? state.items.filter((it) => !!starredMap[it.fileKey]).length
        : 0;
      btn.classList.toggle("active", !!(PCONV.fileDrawerOpen && String(PCONV.fileDrawerSessionKey || "") === key));
      total.style.display = "inline";
      total.textContent = countConversationFilesText(count);
      starWrap.style.display = "inline-flex";
      starCount.textContent = String(starred);
      btn.onclick = () => {
        const same = PCONV.fileDrawerOpen && String(PCONV.fileDrawerSessionKey || "") === key;
        if (same) {
          PCONV.fileDrawerOpen = false;
          renderConversationFileDrawer();
          renderConversationFileEntry(ctx);
          return;
        }
        PCONV.taskDrawerOpen = false;
        if (typeof closeConversationTaskDetailViewer === "function") closeConversationTaskDetailViewer();
        if (typeof renderConversationTaskDrawer === "function") renderConversationTaskDrawer();
        if (typeof currentConversationTaskPayload === "function" && typeof renderConversationTaskEntry === "function") {
          const taskPayload = currentConversationTaskPayload();
          renderConversationTaskEntry(taskPayload.ctx, taskPayload);
        }
        PCONV.fileDrawerOpen = true;
        PCONV.fileDrawerSessionKey = key;
        refreshConversationFilesFromCurrentTimeline();
        renderConversationFileDrawer();
        renderConversationFileEntry(ctx);
      };
    }

    function buildConversationFileSourceText(item) {
      if (!item || typeof item !== "object") return "";
      const parts = [];
      const ts = compactDateTime(item.lastSeenAt || item.firstSeenAt || "");
      if (ts) parts.push(ts);
      const sender = String(item.lastSenderName || item.lastSenderType || "").trim();
      if (sender) parts.push(sender);
      const mk = String(item.lastMessageKind || "").trim();
      if (mk) parts.push(mk);
      const line = parts.join(" · ");
      const sourceRef = String(item.lastSourceRefText || "").trim();
      const callbackTo = String(item.lastCallbackToText || "").trim();
      const extra = [];
      if (sourceRef) extra.push("来源 " + sourceRef);
      if (callbackTo) extra.push("回执 " + callbackTo);
      return [line, extra.join(" · ")].filter(Boolean).join("\n");
    }

    function refreshConversationFilesFromTimeline(ctx, root) {
      if (!ctx || !ctx.projectId || !ctx.sessionId || !root || !root.querySelectorAll) return;
      const key = convComposerDraftKey(ctx.projectId, ctx.sessionId);
      const nodes = Array.from(root.querySelectorAll(".msg-object-link, .msg-object-code-target"));
      const map = new Map();
      nodes.forEach((node) => {
        const obj = node && node.__messageObject;
        if (!isCollectableConversationFileObject(obj)) return;
        const fileKey = buildConversationFileObjectKey(obj);
        if (!fileKey) return;
        const row = node.closest(".msgrow");
        const meta = row && row.__conversationFileMeta && typeof row.__conversationFileMeta === "object"
          ? row.__conversationFileMeta
          : {};
        const nowTs = String(meta.createdAt || "").trim();
        let item = map.get(fileKey);
        if (!item) {
          item = {
            fileKey,
            title: conversationFileTitleFromObject(obj),
            label: String(obj.label || obj.value || "").trim(),
            path: String(obj.path || "").trim(),
            openUrl: String(obj.openUrl || "").trim(),
            kind: String(obj.kind || "").trim(),
            tone: String(obj.tone || "").trim(),
            typeLabel: conversationFileTypeLabel(obj),
            mentionCount: 0,
            firstSeenAt: nowTs,
            lastSeenAt: nowTs,
            lastSenderName: "",
            lastSenderType: "",
            lastMessageKind: "",
            lastSourceRefText: "",
            lastCallbackToText: "",
            object: {
              kind: String(obj.kind || ""),
              tone: String(obj.tone || ""),
              value: String(obj.value || ""),
              label: String(obj.label || obj.value || ""),
              path: String(obj.path || ""),
              openUrl: String(obj.openUrl || ""),
              defaultAction: String(obj.defaultAction || ""),
            },
          };
          map.set(fileKey, item);
        }
        item.mentionCount += 1;
        if (nowTs) {
          const prevLast = toTimeNum(item.lastSeenAt);
          const nextLast = toTimeNum(nowTs);
          if (prevLast < 0 || (nextLast >= 0 && nextLast >= prevLast)) {
            item.lastSeenAt = nowTs;
            item.lastSenderName = String(meta.senderName || "").trim();
            item.lastSenderType = String(meta.senderType || "").trim();
            item.lastMessageKind = String(meta.messageKind || "").trim();
            item.lastSourceRefText = String(meta.sourceRefText || "").trim();
            item.lastCallbackToText = String(meta.callbackToText || "").trim();
          }
          const prevFirst = toTimeNum(item.firstSeenAt);
          const nextFirst = toTimeNum(nowTs);
          if (prevFirst < 0 || (nextFirst >= 0 && nextFirst < prevFirst)) {
            item.firstSeenAt = nowTs;
          }
        }
      });
      const items = Array.from(map.values()).sort((a, b) => {
        const ta = toTimeNum(a.lastSeenAt);
        const tb = toTimeNum(b.lastSeenAt);
        if (ta >= 0 && tb >= 0 && ta !== tb) return tb - ta;
        if (Number(a.mentionCount || 0) !== Number(b.mentionCount || 0)) {
          return Number(b.mentionCount || 0) - Number(a.mentionCount || 0);
        }
        return String(a.title || "").localeCompare(String(b.title || ""));
      });
      PCONV.filesBySessionKey[key] = {
        count: items.length,
        items,
        updatedAt: new Date().toISOString(),
        fetchedAt: Date.now(),
      };
    }

    function refreshConversationFilesFromCurrentTimeline() {
      const ctx = currentConversationCtx();
      const timeline = document.getElementById("convTimeline");
      if (!ctx || !timeline) return;
      refreshConversationFilesFromTimeline(ctx, timeline);
      renderConversationFileUi();
    }

    function toggleConversationFileStar(key, fileKey) {
      const draftKey = String(key || "").trim();
      const oneFileKey = String(fileKey || "").trim();
      if (!draftKey || !oneFileKey) return;
      const starredMap = getConversationFileStarredMapByKey(draftKey);
      if (starredMap[oneFileKey]) delete starredMap[oneFileKey];
      else starredMap[oneFileKey] = true;
      persistConversationFileStarredMap();
      renderConversationFileUi();
    }

    async function revealConversationFileInFinder(item) {
      const path = String(item && item.path || "").trim();
      if (!path) return;
      try {
        const resp = await fetch("/api/fs/reveal", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ path }),
        });
        if (!resp.ok) throw new Error((await parseResponseDetail(resp)) || ("HTTP " + resp.status));
        setHintText("conv", "已打开 Finder 定位");
      } catch (err) {
        setHintText("conv", "打开 Finder 失败：" + String((err && err.message) || err || "未知错误"));
      }
    }

    function renderConversationFileDrawer() {
      const mask = document.getElementById("convFileDrawerMask");
      const list = document.getElementById("convFileList");
      const sub = document.getElementById("convFileDrawerSub");
      const hint = document.getElementById("convFileHint");
      const onlyStarBtn = document.getElementById("convFileOnlyStarredBtn");
      const refreshBtn = document.getElementById("convFileRefreshBtn");
      const sortSelect = document.getElementById("convFileSortSelect");
      if (!mask || !list || !sub || !hint || !onlyStarBtn || !refreshBtn || !sortSelect) return;
      if (!PCONV.fileDrawerOpen) {
        mask.classList.remove("show");
        return;
      }
      mask.classList.add("show");
      const key = String(PCONV.fileDrawerSessionKey || currentConvComposerDraftKey() || "").trim();
      if (!key) return;
      PCONV.fileDrawerSessionKey = key;
      const state = getConversationFileStateByKey(key);
      const items = Array.isArray(state.items) ? state.items.slice() : [];
      const starredMap = getConversationFileStarredMapByKey(key);
      const onlyStarred = !!PCONV.fileOnlyStarredBySessionKey[key];
      const sortMode = getConversationFileSortByKey(key);
      const activeTypes = getConversationFileTypeFilterByKey(key);
      const activeTypeSet = new Set(activeTypes);
      const filterLabelMap = conversationFileFilterLabelMap();
      const starredCount = items.filter((it) => !!starredMap[it.fileKey]).length;
      const sortedItems = items.slice().sort((a, b) => {
        if (sortMode === "mention_desc" && Number(a.mentionCount || 0) !== Number(b.mentionCount || 0)) {
          return Number(b.mentionCount || 0) - Number(a.mentionCount || 0);
        }
        if (sortMode === "name_asc") {
          return String(a.title || "").localeCompare(String(b.title || ""));
        }
        const ta = toTimeNum(a.lastSeenAt);
        const tb = toTimeNum(b.lastSeenAt);
        if (ta >= 0 && tb >= 0 && ta !== tb) return sortMode === "time_asc" ? (ta - tb) : (tb - ta);
        if (Number(a.mentionCount || 0) !== Number(b.mentionCount || 0)) {
          return Number(b.mentionCount || 0) - Number(a.mentionCount || 0);
        }
        return String(a.title || "").localeCompare(String(b.title || ""));
      });
      const filteredItems = sortedItems.filter((it) => activeTypeSet.has(conversationFileFilterCategory(it)));
      const visibleItems = onlyStarred ? filteredItems.filter((it) => starredMap[it.fileKey]) : filteredItems;
      const currentCtx = currentConversationCtx();
      const channelName = currentCtx ? String(currentCtx.channelName || currentCtx.alias || "当前会话") : "当前会话";
      sub.textContent = channelName + " · 共 " + items.length + " 个文件" + (starredCount ? (" · 收藏 " + starredCount) : "");
      renderConversationFileFilterBar(key, items);
      const selectedTypeText = activeTypes.map((it) => filterLabelMap[it] || it).join(" / ");
      const defaultFilterEmpty = !onlyStarred && !filteredItems.length && items.length > 0;
      hint.textContent = onlyStarred
        ? ("当前仅展示已收藏文件；类型筛选：" + selectedTypeText + "。")
        : (defaultFilterEmpty
            ? ("已识别到 " + items.length + " 个文件，但默认筛选「" + selectedTypeText + "」没有命中；点上方“全部”可查看全部文件。")
            : ("默认仅看给人看的文件类型，当前筛选：" + selectedTypeText + "。"));
      onlyStarBtn.textContent = onlyStarred ? "查看全部" : "仅收藏";
      onlyStarBtn.classList.toggle("primary", onlyStarred);
      sortSelect.value = sortMode;
      refreshBtn.disabled = false;
      list.innerHTML = "";
      if (!items.length) {
        list.appendChild(el("div", { class: "memo-empty", text: "当前会话还没有识别到文件提及。" }));
        return;
      }
      if (!visibleItems.length) {
        list.appendChild(el("div", {
          class: "memo-empty",
          text: onlyStarred
            ? "当前筛选下没有已收藏文件。"
            : ("已识别到 " + items.length + " 个文件，但默认筛选「" + selectedTypeText + "」没有命中；点上方“全部”查看全部文件。"),
        }));
        return;
      }
      visibleItems.forEach((item) => {
        const row = el("div", { class: "conv-file-item" });
        const head = el("div", { class: "conv-file-head" });
        const headMain = el("div", { class: "conv-file-head-main" });
        const iconMeta = conversationFileIconMeta(item);
        headMain.appendChild(el("span", {
          class: "conv-file-icon tone-" + String(iconMeta.tone || "file"),
          text: String(iconMeta.glyph || "FILE"),
        }));
        const titleBox = el("div", { class: "conv-file-titlebox" });
        titleBox.appendChild(el("div", { class: "conv-file-title", text: item.title || "未命名文件" }));
        titleBox.appendChild(el("div", { class: "conv-file-path", text: item.path || item.openUrl || item.label || "-" }));
        headMain.appendChild(titleBox);
        head.appendChild(headMain);
        const starBtn = el("button", {
          class: "conv-file-star" + (starredMap[item.fileKey] ? " active" : ""),
          type: "button",
          text: starredMap[item.fileKey] ? "★" : "☆",
          title: starredMap[item.fileKey] ? "取消收藏" : "标记收藏",
        });
        starBtn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          toggleConversationFileStar(key, item.fileKey);
        });
        head.appendChild(starBtn);
        row.appendChild(head);

        const meta = el("div", { class: "conv-file-meta" });
        meta.appendChild(el("span", { class: "conv-file-chip", text: item.typeLabel || "文件" }));
        meta.appendChild(el("span", { class: "conv-file-chip", text: "提及 " + Number(item.mentionCount || 0) }));
        const lastSeen = compactDateTime(item.lastSeenAt || item.firstSeenAt || "");
        if (lastSeen) meta.appendChild(el("span", { class: "conv-file-chip", text: "最近 " + lastSeen }));
        row.appendChild(meta);

        const sourceText = buildConversationFileSourceText(item);
        if (sourceText) row.appendChild(el("div", { class: "conv-file-source", text: sourceText }));

        const actions = el("div", { class: "conv-file-actions" });
        const previewBtn = el("button", { class: "btn", type: "button", text: "预览" });
        previewBtn.addEventListener("click", () => activateMessageObject(item.object));
        actions.appendChild(previewBtn);
        const openUrl = messageObjectViewerOpenUrl(item.object, null);
        const openBtn = el("button", { class: "btn", type: "button", text: "新标签打开" });
        openBtn.disabled = !openUrl || item.typeLabel === "目录";
        openBtn.addEventListener("click", () => {
          if (!openUrl) return;
          openNew(openUrl);
        });
        actions.appendChild(openBtn);
        const revealBtn = el("button", { class: "btn", type: "button", text: "定位 Finder" });
        revealBtn.disabled = !String(item.path || "").trim();
        revealBtn.addEventListener("click", () => { revealConversationFileInFinder(item); });
        actions.appendChild(revealBtn);
        row.appendChild(actions);
        list.appendChild(row);
      });
    }

    function renderConversationFileUi() {
      const ctx = currentConversationCtx();
      if (ctx) renderConversationFileEntry(ctx);
      else hideConversationFileEntry();
      renderConversationFileDrawer();
    }

    function closeConversationFileDrawer() {
      PCONV.fileDrawerOpen = false;
      renderConversationFileUi();
    }

    function toggleConversationFileOnlyStarred() {
      const key = String(PCONV.fileDrawerSessionKey || currentConvComposerDraftKey() || "").trim();
      if (!key) return;
      PCONV.fileOnlyStarredBySessionKey[key] = !PCONV.fileOnlyStarredBySessionKey[key];
      renderConversationFileDrawer();
    }

    function initConversationFileUi() {
      const mask = document.getElementById("convFileDrawerMask");
      const closeBtn = document.getElementById("convFileCloseBtn");
      const refreshBtn = document.getElementById("convFileRefreshBtn");
      const onlyStarBtn = document.getElementById("convFileOnlyStarredBtn");
      const sortSelect = document.getElementById("convFileSortSelect");
      if (mask) {
        mask.addEventListener("click", (e) => {
          if (e.target === mask) closeConversationFileDrawer();
        });
      }
      if (closeBtn) closeBtn.addEventListener("click", closeConversationFileDrawer);
      if (refreshBtn) refreshBtn.addEventListener("click", refreshConversationFilesFromCurrentTimeline);
      if (onlyStarBtn) onlyStarBtn.addEventListener("click", toggleConversationFileOnlyStarred);
      if (sortSelect) {
        sortSelect.addEventListener("change", () => {
          const key = String(PCONV.fileDrawerSessionKey || currentConvComposerDraftKey() || "").trim();
          if (!key) return;
          setConversationFileSortByKey(key, sortSelect.value);
          renderConversationFileDrawer();
        });
      }
    }

    async function sendConversationMessage() {
      if (typeof isTaskShareModeActive === "function" && isTaskShareModeActive()) {
        return await sendTaskShareModeMessage();
      }
      const input = document.getElementById("convMsg");
      const sendBtn = document.getElementById("convSendBtn");
      const hint = document.getElementById("convHint");
      if (!input || !sendBtn || !hint) return false;
      saveConvComposerUiToBoundDraft();
      const composeDraftKey = String(PCONV.composerBoundDraftKey || "").trim();
      const composeDraft = getConvComposerDraftByKey(composeDraftKey);
      const composeAttachments = cloneConvComposerAttachments(composeDraft.attachments);
      const mentionTargets = serializeMentionTargetsForSend(composeDraft.mentions);
      const replyContext = normalizeConvReplyContext(composeDraft.replyContext);
      // 发送目标以右侧当前可见会话为真源，只有当前上下文缺失时才回退默认路由。
      // 否则会出现“视觉上切到子会话，但发送仍落到主会话”的错投。
      const ctx = currentConversationCtx() || resolveConversationSendCtx();
      if (!ctx || !ctx.sessionId || !ctx.channelName) {
        input.placeholder = "该会话缺少通道路由，请先为该 session 绑定通道";
        return false;
      }
      const message = String(composeDraft.text || "").trim();
      if (!message && composeAttachments.length === 0) return false;
      const outboundMessage = appendMentionCompatToMessage(message, mentionTargets);

      if (String(STATE.selectedSessionId || "") !== String(ctx.sessionId || "")) {
        setSelectedSessionId(ctx.sessionId, true, { explicit: false });
      }

      PCONV.sending = true;
      PCONV.optimistic = {
        sessionId: ctx.sessionId,
        message: outboundMessage,
        attachments: composeAttachments.map((a) => ({ url: a.url || a.dataUrl || "", originalName: a.originalName })),
        mentionTargets,
        replyToRunId: String((replyContext && replyContext.runId) || ""),
        createdAt: new Date().toISOString(),
      };
      markSessionPending(ctx.sessionId, outboundMessage);
      if (STATE.panelMode === "conv") {
        buildConversationLeftList();
        buildConversationMainList(document.getElementById("fileList"));
      } else {
        buildChannelConversationList();
      }
      sendBtn.disabled = true;
      sendBtn.textContent = "发送中...";
      const routeHint = ctx.routeReason === "explicit-sub"
        ? "发送中（子会话）…"
        : "发送中（主会话默认路由）…";
      setHintText("conv", routeHint);
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
            message: outboundMessage,
            ...buildUiUserSenderFields(),
            attachments: composeAttachments.map((a) => ({
              filename: a.filename,
              originalName: a.originalName,
              url: a.url || a.dataUrl || "",
            })),
            mention_targets: mentionTargets,
            reply_to_run_id: String((replyContext && replyContext.runId) || ""),
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
          clearConvComposerDraftByKey(composeDraftKey);
          if (String(PCONV.composerBoundDraftKey || "") === composeDraftKey) {
            resetMessageInputHeight(input);
          }
          const resp = await r.json().catch(() => ({}));
          const runId = resp && resp.run ? String(resp.run.id || "") : "";
          injectConversationAckRunToTimeline(
            ctx,
            PCONV.optimistic || {},
            resp || {},
            { source: "announce-ack" }
          );
          if (typeof triggerConversationEasterEggForText === "function") {
            triggerConversationEasterEggForText(outboundMessage, {
              sessionId: ctx.sessionId,
              runId,
              source: "send-ack",
            });
          }
          PCONV.optimistic = null;
          PCONV.sending = false;
          const doneHint = ctx.routeReason === "explicit-sub"
            ? "已发送到子会话，等待执行回溯刷新…"
            : "已发送到主会话，等待执行回溯刷新…";
          setHintText("conv", doneHint);
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

    function applyConversationMemosToComposer(items, key) {
      const draftKey = String(key || currentConvComposerDraftKey() || "").trim();
      if (!draftKey) return;
      const rows = Array.isArray(items) ? items.slice() : [];
      rows.sort((a, b) => String(a.createdAt || "").localeCompare(String(b.createdAt || "")));
      updateConvComposerDraftByKey(draftKey, (d) => {
        const parts = [];
        const baseText = String(d.text || "").trim();
        if (baseText) parts.push(baseText);
        for (const it of rows) {
          const txt = String((it && it.text) || "").trim();
          if (txt) parts.push(txt);
        }
        d.text = parts.join("\n\n");
        const incoming = [];
        rows.forEach((it) => {
          const atts = Array.isArray(it && it.attachments) ? it.attachments : [];
          atts.forEach((att) => incoming.push(att));
        });
        d.attachments = mergeMemoAttachments(d.attachments, incoming);
      });
      const consumedIds = rows.map((it) => String((it && it.id) || "").trim()).filter(Boolean);
      if (consumedIds.length) markConversationMemosConsumedByKey(draftKey, consumedIds);
      if (String(PCONV.composerBoundDraftKey || "") === draftKey) {
        applyConvComposerDraftToUiByKey(draftKey, { focus: true });
      }
      setConversationMemoHintByKey(draftKey, "已放入输入框，可继续编辑后手动发送。");
      renderConversationMemoUi();
    }

    async function saveCurrentComposerAsMemo() {
      saveConvComposerUiToBoundDraft();
      const key = String(currentConvComposerDraftKey() || "").trim();
      if (!key) return;
      const split = key.split("::");
      const projectId = split[0] || "";
      const sessionId = split.slice(1).join("::");
      const draft = getConvComposerDraftByKey(key);
      const text = String(draft.text || "").trim();
      const attachments = cloneConvComposerAttachments(draft.attachments).map((att) => ({
        filename: att.filename,
        originalName: att.originalName,
        url: att.url || att.dataUrl || "",
      }));
      if (!text && attachments.length <= 0) {
        setHintText("conv", "当前输入框为空，无法记录备忘。");
        return;
      }
      PCONV.memoActionBusyBySessionKey[key] = "save";
      setConversationMemoHintByKey(key, "正在保存备忘...");
      renderConversationMemoUi();
      try {
        const resp = await createConversationMemo({ projectId, sessionId, text, attachments });
        const item = normalizeConversationMemoItem(resp && resp.item);
        const state = getConversationMemoStateByKey(key);
        const items = Array.isArray(state.items) ? state.items.slice() : [];
        if (item) items.unshift(item);
        const dedup = [];
        const seen = new Set();
        for (const it of items) {
          const id = String(it && it.id || "");
          if (!id || seen.has(id)) continue;
          seen.add(id);
          dedup.push(it);
        }
        const count = Math.max(Number(resp && resp.count || dedup.length || 0), dedup.length);
        PCONV.memoBySessionKey[key] = {
          count,
          items: dedup,
          updatedAt: item ? item.updatedAt : String(state.updatedAt || ""),
          fetchedAt: Date.now(),
        };
        if (item && item.id) {
          const consumed = getConversationMemoConsumedMapByKey(key);
          if (consumed[item.id]) {
            delete consumed[item.id];
            persistConversationMemoConsumedMap();
          }
        }
        clearConvComposerDraftByKey(key);
        setConversationMemoHintByKey(key, "已记录备忘并清空输入框，当前会话共 " + count + " 条。");
        setHintText("conv", "已记录备忘并清空输入框。");
      } catch (e) {
        const msg = String((e && e.message) || e || "未知错误");
        setConversationMemoHintByKey(key, "记录失败：" + msg);
      } finally {
        delete PCONV.memoActionBusyBySessionKey[key];
        renderConversationMemoUi();
      }
    }

    function parseConversationMemoKey(key) {
      const raw = String(key || "").trim();
      if (!raw) return { projectId: "", sessionId: "" };
      const idx = raw.indexOf("::");
      if (idx < 0) return { projectId: "", sessionId: "" };
      return {
        projectId: raw.slice(0, idx),
        sessionId: raw.slice(idx + 2),
      };
    }

    function closeConversationMemoDrawer() {
      PCONV.memoDrawerOpen = false;
      renderConversationMemoDrawer();
    }

    function toggleSelectAllConversationMemos() {
      const key = String(PCONV.memoDrawerSessionKey || currentConvComposerDraftKey() || "").trim();
      if (!key) return;
      const state = getConversationMemoStateByKey(key);
      const items = Array.isArray(state.items) ? state.items : [];
      const selectedMap = getConversationMemoSelectedMapByKey(key);
      const selectedCount = items.filter((it) => selectedMap[it.id]).length;
      if (selectedCount === items.length) {
        PCONV.memoSelectedBySessionKey[key] = Object.create(null);
      } else {
        const next = Object.create(null);
        items.forEach((it) => { next[it.id] = true; });
        PCONV.memoSelectedBySessionKey[key] = next;
      }
      renderConversationMemoDrawer();
    }

    function applySelectedConversationMemos() {
      const key = String(PCONV.memoDrawerSessionKey || currentConvComposerDraftKey() || "").trim();
      if (!key) return;
      const state = getConversationMemoStateByKey(key);
      const selectedMap = getConversationMemoSelectedMapByKey(key);
      const rows = (Array.isArray(state.items) ? state.items : []).filter((it) => selectedMap[it.id]);
      if (!rows.length) {
        setConversationMemoHintByKey(key, "请先勾选至少一条备忘。");
        renderConversationMemoDrawer();
        return;
      }
      applyConversationMemosToComposer(rows, key);
    }

    async function applyAndDeleteConversationMemosByRows(key, rows) {
      const draftKey = String(key || currentConvComposerDraftKey() || "").trim();
      if (!draftKey) return;
      const parsed = parseConversationMemoKey(draftKey);
      if (!parsed.projectId || !parsed.sessionId) return;
      const picked = (Array.isArray(rows) ? rows : [])
        .filter((it) => it && String(it.id || "").trim())
        .map((it) => it);
      if (!picked.length) {
        setConversationMemoHintByKey(draftKey, "请先勾选至少一条备忘。");
        renderConversationMemoDrawer();
        return;
      }
      const ids = picked.map((it) => String(it.id || "").trim()).filter(Boolean);
      if (!ids.length) return;

      applyConversationMemosToComposer(picked, draftKey);
      PCONV.memoActionBusyBySessionKey[draftKey] = "apply-delete";
      setConversationMemoHintByKey(draftKey, "已放入输入框，正在删除备忘...");
      renderConversationMemoDrawer();
      try {
        await deleteConversationMemos({
          projectId: parsed.projectId,
          sessionId: parsed.sessionId,
          ids,
        });
        const selectedMap = getConversationMemoSelectedMapByKey(draftKey);
        ids.forEach((id) => { delete selectedMap[id]; });
        await ensureConversationMemosLoaded(parsed.projectId, parsed.sessionId, { force: true });
        setConversationMemoHintByKey(draftKey, "已放入输入框，并删除 " + ids.length + " 条备忘。");
      } catch (e) {
        const msg = String((e && e.message) || e || "未知错误");
        setConversationMemoHintByKey(draftKey, "已放入输入框，但删除失败：" + msg);
      } finally {
        delete PCONV.memoActionBusyBySessionKey[draftKey];
        renderConversationMemoDrawer();
      }
    }

    function applyDeleteSelectedConversationMemos() {
      const key = String(PCONV.memoDrawerSessionKey || currentConvComposerDraftKey() || "").trim();
      if (!key) return;
      const state = getConversationMemoStateByKey(key);
      const selectedMap = getConversationMemoSelectedMapByKey(key);
      const rows = (Array.isArray(state.items) ? state.items : []).filter((it) => selectedMap[it.id]);
      if (!rows.length) {
        setConversationMemoHintByKey(key, "请先勾选至少一条备忘。");
        renderConversationMemoDrawer();
        return;
      }
      applyAndDeleteConversationMemosByRows(key, rows);
    }

    async function sendAndDeleteConversationMemosByRows(key, rows) {
      const draftKey = String(key || currentConvComposerDraftKey() || "").trim();
      if (!draftKey) return;
      const parsed = parseConversationMemoKey(draftKey);
      if (!parsed.projectId || !parsed.sessionId) return;
      const picked = (Array.isArray(rows) ? rows : [])
        .filter((it) => it && String(it.id || "").trim())
        .map((it) => it);
      if (!picked.length) {
        setConversationMemoHintByKey(draftKey, "请先勾选至少一条备忘。");
        renderConversationMemoDrawer();
        return;
      }
      const ids = picked.map((it) => String(it.id || "").trim()).filter(Boolean);
      if (!ids.length) return;

      applyConversationMemosToComposer(picked, draftKey);
      PCONV.memoActionBusyBySessionKey[draftKey] = "send-delete";
      setConversationMemoHintByKey(draftKey, "已放入输入框，正在发送...");
      renderConversationMemoDrawer();
      const sentOk = await sendConversationMessage();
      if (!sentOk) {
        delete PCONV.memoActionBusyBySessionKey[draftKey];
        setConversationMemoHintByKey(draftKey, "发送失败，已保留备忘，可修改后重试。");
        renderConversationMemoDrawer();
        return;
      }

      setConversationMemoHintByKey(draftKey, "发送成功，正在删除备忘...");
      renderConversationMemoDrawer();
      try {
        await deleteConversationMemos({
          projectId: parsed.projectId,
          sessionId: parsed.sessionId,
          ids,
        });
        const selectedMap = getConversationMemoSelectedMapByKey(draftKey);
        ids.forEach((id) => { delete selectedMap[id]; });
        await ensureConversationMemosLoaded(parsed.projectId, parsed.sessionId, { force: true });
        setConversationMemoHintByKey(draftKey, "已发送并删除 " + ids.length + " 条备忘。");
      } catch (e) {
        const msg = String((e && e.message) || e || "未知错误");
        setConversationMemoHintByKey(draftKey, "发送成功，但删除失败：" + msg);
      } finally {
        delete PCONV.memoActionBusyBySessionKey[draftKey];
        renderConversationMemoDrawer();
      }
    }

    function applySendDeleteSelectedConversationMemos() {
      const key = String(PCONV.memoDrawerSessionKey || currentConvComposerDraftKey() || "").trim();
      if (!key) return;
      const state = getConversationMemoStateByKey(key);
      const selectedMap = getConversationMemoSelectedMapByKey(key);
      const rows = (Array.isArray(state.items) ? state.items : []).filter((it) => selectedMap[it.id]);
      if (!rows.length) {
        setConversationMemoHintByKey(key, "请先勾选至少一条备忘。");
        renderConversationMemoDrawer();
        return;
      }
      sendAndDeleteConversationMemosByRows(key, rows);
    }

    async function deleteSelectedConversationMemos() {
      const key = String(PCONV.memoDrawerSessionKey || currentConvComposerDraftKey() || "").trim();
      if (!key) return;
      const state = getConversationMemoStateByKey(key);
      const selectedMap = getConversationMemoSelectedMapByKey(key);
      const ids = (Array.isArray(state.items) ? state.items : [])
        .filter((it) => selectedMap[it.id])
        .map((it) => it.id);
      if (!ids.length) {
        setConversationMemoHintByKey(key, "请先勾选要删除的备忘。");
        renderConversationMemoDrawer();
        return;
      }
      const parsed = parseConversationMemoKey(key);
      if (!parsed.projectId || !parsed.sessionId) return;
      PCONV.memoActionBusyBySessionKey[key] = "delete";
      setConversationMemoHintByKey(key, "正在删除备忘...");
      renderConversationMemoDrawer();
      try {
        await deleteConversationMemos({
          projectId: parsed.projectId,
          sessionId: parsed.sessionId,
          ids,
        });
        PCONV.memoSelectedBySessionKey[key] = Object.create(null);
        await ensureConversationMemosLoaded(parsed.projectId, parsed.sessionId, { force: true });
        setConversationMemoHintByKey(key, "已删除 " + ids.length + " 条备忘。");
      } catch (e) {
        const msg = String((e && e.message) || e || "未知错误");
        setConversationMemoHintByKey(key, "删除失败：" + msg);
      } finally {
        delete PCONV.memoActionBusyBySessionKey[key];
        renderConversationMemoDrawer();
      }
    }

    async function clearConversationMemosInDrawer() {
      const key = String(PCONV.memoDrawerSessionKey || currentConvComposerDraftKey() || "").trim();
      if (!key) return;
      const parsed = parseConversationMemoKey(key);
      if (!parsed.projectId || !parsed.sessionId) return;
      const ok = confirm("确认清空当前会话全部备忘吗？此操作不可撤销。");
      if (!ok) return;
      PCONV.memoActionBusyBySessionKey[key] = "clear";
      setConversationMemoHintByKey(key, "正在清空备忘...");
      renderConversationMemoDrawer();
      try {
        await clearConversationMemos({
          projectId: parsed.projectId,
          sessionId: parsed.sessionId,
        });
        PCONV.memoSelectedBySessionKey[key] = Object.create(null);
        await ensureConversationMemosLoaded(parsed.projectId, parsed.sessionId, { force: true });
        setConversationMemoHintByKey(key, "当前会话备忘已清空。");
      } catch (e) {
        const msg = String((e && e.message) || e || "未知错误");
        setConversationMemoHintByKey(key, "清空失败：" + msg);
      } finally {
        delete PCONV.memoActionBusyBySessionKey[key];
        renderConversationMemoDrawer();
      }
    }

    function initConversationMemoUi() {
      const mask = document.getElementById("convMemoDrawerMask");
      const closeBtn = document.getElementById("convMemoCloseBtn");
      const selectAllBtn = document.getElementById("convMemoSelectAllBtn");
      const applyBtn = document.getElementById("convMemoApplyBtn");
      const applyDeleteBtn = document.getElementById("convMemoApplyDeleteBtn");
      const sendDeleteBtn = document.getElementById("convMemoSendDeleteBtn");
      const deleteBtn = document.getElementById("convMemoDeleteBtn");
      const clearBtn = document.getElementById("convMemoClearBtn");
      if (mask) {
        mask.addEventListener("click", (e) => {
          if (e.target === mask) closeConversationMemoDrawer();
        });
      }
      if (closeBtn) closeBtn.addEventListener("click", closeConversationMemoDrawer);
      if (selectAllBtn) selectAllBtn.addEventListener("click", toggleSelectAllConversationMemos);
      if (applyBtn) applyBtn.addEventListener("click", applySelectedConversationMemos);
      if (applyDeleteBtn) applyDeleteBtn.addEventListener("click", applyDeleteSelectedConversationMemos);
      if (sendDeleteBtn) sendDeleteBtn.addEventListener("click", applySendDeleteSelectedConversationMemos);
      if (deleteBtn) deleteBtn.addEventListener("click", () => { deleteSelectedConversationMemos(); });
      if (clearBtn) clearBtn.addEventListener("click", () => { clearConversationMemosInDrawer(); });
    }

    function stopCCBPoll() {
      if (CCB.pollTimer) {
        clearTimeout(CCB.pollTimer);
        CCB.pollTimer = 0;
      }
    }

    function scheduleCCBPoll(ms = 1500) {
      stopCCBPoll();
      CCB.pollTimer = setTimeout(() => {
        refreshCCB();
      }, ms);
    }

    function ccbPollDelay(hasWorking) {
      if (!hasWorking) return 0;
      if (typeof document !== "undefined" && document.hidden) return 60000;
      return 10000;
    }

    function stopConversationPoll() {
      if (PCONV.pollTimer) {
        clearTimeout(PCONV.pollTimer);
        PCONV.pollTimer = 0;
      }
    }

    function scheduleConversationPoll(ms = 5000) {
      stopConversationPoll();
      PCONV.pollTimer = setTimeout(() => {
        refreshConversationPanel();
      }, ms);
    }

    function ensureConversationPollingGovernanceStateMaps() {
      if (!PCONV.pollFailureCountByProject || typeof PCONV.pollFailureCountByProject !== "object") {
        PCONV.pollFailureCountByProject = Object.create(null);
      }
    }

    function getConversationPollingPolicy(projectId = "") {
      const pid = String(projectId || STATE.project || "").trim();
      const hints = typeof conversationProjectPollingHints === "function"
        ? conversationProjectPollingHints(pid)
        : null;
      return {
        projectId: pid,
        enabled: !!(hints && hints.enabled),
        poll_interval_ms: Math.max(0, Number(hints && hints.poll_interval_ms) || 45000),
        hidden_poll_interval_ms: Math.max(0, Number(hints && hints.hidden_poll_interval_ms) || 90000),
        backoff_step_ms: Math.max(0, Number(hints && hints.backoff_step_ms) || 2000),
        backoff_max_ms: Math.max(0, Number(hints && hints.backoff_max_ms) || 15000),
        pause_when_hidden: !!(hints && hints.pause_when_hidden),
      };
    }

    function conversationPollDelay(projectIdOrHasWorking, hasWorkingArg) {
      const projectId = typeof projectIdOrHasWorking === "string"
        ? projectIdOrHasWorking
        : String(STATE.project || "").trim();
      const hasWorking = typeof projectIdOrHasWorking === "string"
        ? !!hasWorkingArg
        : !!projectIdOrHasWorking;
      if (PCONV.sending) return 4000;
      const policy = getConversationPollingPolicy(projectId);
      if (policy.enabled) {
        if (typeof document !== "undefined" && document.hidden && policy.pause_when_hidden) return 0;
        ensureConversationPollingGovernanceStateMaps();
        const failureCount = Math.max(0, Number(PCONV.pollFailureCountByProject[policy.projectId] || 0) || 0);
        const baseDelay = (typeof document !== "undefined" && document.hidden)
          ? policy.hidden_poll_interval_ms
          : policy.poll_interval_ms;
        if (failureCount > 0) {
          return Math.min(
            baseDelay + (failureCount * policy.backoff_step_ms),
            Math.max(baseDelay, policy.backoff_max_ms)
          );
        }
        return baseDelay;
      }
      if (hasWorking) {
        if (typeof document !== "undefined" && document.hidden) return 45000;
        return 10000;
      }
      if (typeof document !== "undefined" && document.hidden) return 90000;
      return 45000;
    }

    function triggerConversationRefreshOnResume() {
      const projectId = String(STATE.project || "").trim();
      if (!projectId || projectId === "overview") return;
      if (STATE.panelMode !== "conv" && STATE.panelMode !== "channel") return;
      if (PCONV.busy) return;
      refreshConversationPanel();
    }

    function ensureRunExpanded(runId) {
      const id = String(runId || "");
      if (!id) return;
      CCB.expanded.add(id);
      if (CCB.detailMap[id]) return;
      CCB.detailMap[id] = {
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
      loadRun(id).then((full) => {
        CCB.detailMap[id] = {
          loading: false,
          full: full || null,
          message: String((full && full.message) || ""),
          process: String((full && full.logTail) || ""),
          last: String((full && full.lastMessage) || ""),
          partial: String((full && full.partialMessage) || ""),
          errorHint: String((full && full.errorHint) || ""),
          agentMessages: Array.isArray(full && full.agentMessages) ? full.agentMessages : [],
          status: String((full && full.run && full.run.status) || ""),
          startedAt: String((full && full.run && full.run.startedAt) || ""),
          finishedAt: String((full && full.run && full.run.finishedAt) || ""),
          runError: String((full && full.run && full.run.error) || ""),
          error: "",
        };
        renderRuns(CCB.runs);
      }).catch((e) => {
        CCB.detailMap[id] = {
          loading: false,
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
          error: String(e || "load failed"),
        };
        renderRuns(CCB.runs);
      });
    }

    function collapseRun(runId) {
      const id = String(runId || "");
      if (!id) return;
      CCB.expanded.delete(id);
      renderRuns(CCB.runs);
    }

    function currentChannelCtx(it) {
      const projectId = it ? String(it.project_id || "") : String(STATE.project || "");
      const channelName = it ? String(it.channel || "") : String(STATE.channel || "");
      const sess = (projectId && channelName && projectId !== "overview") ? sessionForChannel(projectId, channelName) : null;
      const sid = sess && sess.session_id ? String(sess.session_id).trim() : "";
      const cliType = sess && sess.cli_type ? String(sess.cli_type).trim() : "codex";
      return { projectId, channelName, session: sess, sessionId: sid, cliType, channelId: projectId + "::" + channelName };
    }

    function restoreConversationDraft(payload) {
      const input = document.getElementById("convMsg");
      if (!input) return;
      const msg = String((payload && payload.message) || "");
      const draftKey = currentConvComposerDraftKey();
      const rawAttachments = Array.isArray(payload && payload.attachments) ? payload.attachments : [];
      const nextAttachments = [];
      for (const att of rawAttachments) {
        const src = resolveAttachmentUrl(att);
        if (!src) continue;
        nextAttachments.push({
          filename: String((att && att.filename) || ""),
          originalName: String((att && (att.originalName || att.filename)) || "attachment"),
          url: src,
          dataUrl: src,
        });
      }
      if (draftKey) {
        updateConvComposerDraftByKey(draftKey, (d) => {
          d.text = msg;
          d.attachments = nextAttachments;
        });
        // 注意：此处不能走 bind(force)。
        // bind(force) 会先把当前输入框旧值回写到同一个草稿 key，导致刚恢复的内容被覆盖。
        if (String(PCONV.composerBoundDraftKey || "").trim() !== draftKey) {
          PCONV.composerBoundDraftKey = draftKey;
        }
        applyConvComposerDraftToUiByKey(draftKey, { focus: true });
      } else {
        input.value = msg;
        if (typeof input.__adjustHeight === "function") input.__adjustHeight();
        else setMessageInputHeight(input);
        renderAttachments();
      }
      try {
        input.focus();
        const len = input.value.length;
        input.setSelectionRange(len, len);
      } catch (_) {}
    }

    async function cancelQueuedRunForEdit(runMeta) {
      const rid = String((runMeta && runMeta.id) || "").trim();
      if (!rid) return;
      if (PCONV.runActionBusy[rid]) return;
      PCONV.runActionBusy[rid] = "cancel_edit";
      renderConversationDetail();
      try {
        setHintText("conv", "正在撤回排队消息…");
        const resp = await callRunAction(rid, "cancel_edit");
        markConversationRunLocallyHidden(rid, true);
        restoreConversationDraft(resp && resp.restored ? resp.restored : {});
        renderConversationDetail(false);
        setHintText("conv", "已撤回到输入框，可编辑后重新发送。");
        Promise.resolve(refreshConversationPanel()).catch(() => {
          scheduleConversationPoll(1200);
        });
      } catch (e) {
        const msg = String((e && e.message) || e || "未知错误");
        const lower = msg.toLowerCase();
        const queuedConflict = /run is (not|no longer) queued/i.test(msg) || (lower.includes("queued") && (lower.includes("not") || lower.includes("no longer")));
        const networkLike = (
          lower.includes("failed to fetch")
          || lower.includes("networkerror")
          || lower.includes("network request failed")
          || lower.includes("load failed")
          || lower.includes("network connection")
          || lower.includes("the internet connection appears to be offline")
        );
        if (queuedConflict) {
          setHintText("conv", "该消息已不在排队态（可能已开始或已完成），正在刷新状态…");
          try {
            await refreshConversationPanel();
          } catch (_) {}
          scheduleConversationPoll(1000);
        } else if (networkLike) {
          setHintText("conv", "撤回请求未确认送达（连接中断或服务重启），已自动刷新最新状态。");
          try {
            await refreshConversationPanel();
          } catch (_) {
            renderConversationDetail();
          }
          scheduleConversationPoll(1200);
        } else {
          if (lower.includes("409")) {
            setHintText("conv", "撤回失败：状态发生变化，已自动刷新最新状态。");
          } else {
            setHintText("conv", "撤回失败：" + msg + "（已刷新状态）");
          }
          try {
            await refreshConversationPanel();
          } catch (_) {
            renderConversationDetail();
          }
          scheduleConversationPoll(1200);
        }
      } finally {
        delete PCONV.runActionBusy[rid];
      }
    }

    async function cancelRetryWaitingRun(runMeta) {
      const rid = String((runMeta && runMeta.id) || "").trim();
      if (!rid) return;
      if (PCONV.runActionBusy[rid]) return;
      PCONV.runActionBusy[rid] = "cancel_retry";
      renderConversationDetail();
      try {
        setHintText("conv", "正在取消自动重试…");
        await callRunAction(rid, "cancel_retry");
        setHintText("conv", "已取消自动重试，后续消息可继续发送。");
        await refreshConversationPanel();
      } catch (e) {
        setHintText("conv", "取消重试失败：" + String((e && e.message) || e || "未知错误"));
        renderConversationDetail();
      } finally {
        delete PCONV.runActionBusy[rid];
      }
    }

    async function interruptRunningRun(runMeta) {
      const rid = String((runMeta && runMeta.id) || "").trim();
      if (!rid) return;
      if (PCONV.runActionBusy[rid]) return;
      PCONV.runActionBusy[rid] = "interrupt";
      renderConversationDetail();
      try {
        setHintText("conv", "正在请求打断执行…");
        await callRunAction(rid, "interrupt");
        setHintText("conv", "已发送打断请求，等待状态回写。");
        await refreshConversationPanel();
        scheduleConversationPoll(1200);
      } catch (e) {
        setHintText("conv", "打断失败：" + String((e && e.message) || e || "未知错误"));
        renderConversationDetail();
      } finally {
        delete PCONV.runActionBusy[rid];
      }
    }
