    // Composer model and permission controls shared by supported CLIs.
    function conversationComposerCliType(ctx, session = null) {
      const context = (ctx && typeof ctx === "object") ? ctx : null;
      const row = (session && typeof session === "object") ? session : null;
      return String(firstNonEmptyText([
        context && context.cliType,
        context && context.cli_type,
        row && row.cli_type,
        row && row.cliType,
      ]) || "").trim().toLowerCase();
    }

    function conversationComposerSupportsModelSwitch(cliTypeRaw) {
      const cliType = String(cliTypeRaw || "").trim();
      return isCodexCliType(cliType)
        || isCodeBuddyCliType(cliType)
        || (typeof isClaudeCliType === "function" && isClaudeCliType(cliType));
    }

    function conversationComposerCliTypesMatch(leftRaw, rightRaw) {
      const left = String(leftRaw || "").trim().toLowerCase();
      const right = String(rightRaw || "").trim().toLowerCase();
      if (!left || !right) return true;
      if (left === right) return true;
      return typeof isClaudeCliType === "function" && isClaudeCliType(left) && isClaudeCliType(right);
    }

    function conversationComposerDefaultModelForCli(cliTypeRaw) {
      const cliType = String(cliTypeRaw || "").trim();
      if (isCodexCliType(cliType)) return codexDefaultModel();
      if (isCodeBuddyCliType(cliType)) return codeBuddyDefaultModel();
      if (typeof isClaudeCliType === "function" && isClaudeCliType(cliType)) {
        return typeof claudeDefaultModel === "function" ? claudeDefaultModel() : "claude-opus-5";
      }
      return "";
    }

    function conversationComposerModelSelectForCli(cliTypeRaw) {
      const cliType = String(cliTypeRaw || "").trim();
      if (isCodexCliType(cliType)) return document.getElementById("convCodexModelInput");
      if (isCodeBuddyCliType(cliType)) return document.getElementById("convCodeBuddyModelSelect");
      if (typeof isClaudeCliType === "function" && isClaudeCliType(cliType)) return document.getElementById("convClaudeModelSelect");
      return null;
    }

    function conversationComposerCachedModelForCli(sessionId, cliTypeRaw) {
      const sid = String(sessionId || "").trim();
      const cliType = String(cliTypeRaw || "").trim();
      if (!sid) return "";
      if (
        isCodexCliType(cliType)
        && PCONV.codexModelBySessionId
        && typeof PCONV.codexModelBySessionId === "object"
      ) {
        return normalizeSessionModel(PCONV.codexModelBySessionId[sid]);
      }
      if (
        isCodeBuddyCliType(cliType)
        && PCONV.codeBuddyModelBySessionId
        && typeof PCONV.codeBuddyModelBySessionId === "object"
      ) {
        return normalizeSessionModel(PCONV.codeBuddyModelBySessionId[sid]);
      }
      if (
        typeof isClaudeCliType === "function"
        && isClaudeCliType(cliType)
        && PCONV.claudeModelBySessionId
        && typeof PCONV.claudeModelBySessionId === "object"
      ) {
        return normalizeSessionModel(PCONV.claudeModelBySessionId[sid]);
      }
      return "";
    }

    function conversationComposerSessionDetailLoadedForModel(sessionId) {
      const sid = String(sessionId || "").trim();
      if (!sid) return false;
      if (PCONV.sessionDetailLoadedAtById && typeof PCONV.sessionDetailLoadedAtById === "object") {
        const loadedAt = Number(PCONV.sessionDetailLoadedAtById[sid] || 0);
        if (loadedAt > 0) return true;
      }
      return false;
    }

    function conversationComposerModelReadiness(ctx, sessionModel = "") {
      const context = (ctx && typeof ctx === "object") ? ctx : null;
      const sid = String((context && context.sessionId) || STATE.selectedSessionId || "").trim();
      const session = sid && typeof findConversationSessionById === "function"
        ? findConversationSessionById(sid)
        : null;
      const cliType = conversationComposerCliType(context, session);
      if (!context || !conversationComposerSupportsModelSwitch(cliType)) {
        return { state: "ready", statusText: "", canUseDefault: false };
      }
      if (normalizeSessionModel(sessionModel)) {
        return { state: "ready", statusText: "", canUseDefault: true };
      }
      if (!sid) {
        return { state: "ready", statusText: "", canUseDefault: true };
      }
      if (conversationComposerSessionDetailLoadedForModel(sid)) {
        return { state: "ready", statusText: "", canUseDefault: true };
      }
      if (typeof isConversationSessionDetailLoading === "function" && isConversationSessionDetailLoading(sid)) {
        return { state: "loading", statusText: "读取中", canUseDefault: false };
      }
      const errorText = typeof getConversationSessionDetailError === "function"
        ? getConversationSessionDetailError(sid)
        : "";
      if (errorText) {
        return { state: "error", statusText: "读取失败", canUseDefault: false, errorText };
      }
      return { state: "missing", statusText: "读取中", canUseDefault: false };
    }

    function conversationComposerModelCanUseDefault(ctx, sessionModel = "") {
      const readiness = conversationComposerModelReadiness(ctx, sessionModel);
      return !!(readiness && readiness.canUseDefault);
    }

    function renderConversationComposerModelLoadingOption(select, text) {
      if (!select) return;
      select.innerHTML = "";
      let option = null;
      if (typeof el === "function") {
        option = el("option", { value: "", text: String(text || "读取模型配置中...") });
      } else if (typeof document !== "undefined" && document.createElement) {
        option = document.createElement("option");
        option.value = "";
        option.textContent = String(text || "读取模型配置中...");
      }
      if (option) select.appendChild(option);
      select.value = "";
    }

    function hydrateConversationComposerModelIfNeeded(ctx, sessionModel = "") {
      const context = (ctx && typeof ctx === "object") ? ctx : null;
      const sid = String((context && context.sessionId) || STATE.selectedSessionId || "").trim();
      const readiness = conversationComposerModelReadiness(context, sessionModel);
      if (!sid || !readiness || readiness.state !== "missing") return;
      if (typeof ensureConversationSessionDetailLoaded !== "function") return;
      ensureConversationSessionDetailLoaded(sid, { force: true, maxAgeMs: 60_000, reason: "composer-model" })
        .then((merged) => {
          if (merged && typeof conversationStoreUpsertSession === "function") {
            conversationStoreUpsertSession(merged, {
              projectId: String((context && context.projectId) || STATE.project || ""),
              source: "session-detail",
            });
          }
          const current = typeof currentConversationCtx === "function" ? currentConversationCtx() : null;
          if (current && String(current.sessionId || "").trim() === sid) {
            if (typeof renderConversationComposerCodexModel === "function") renderConversationComposerCodexModel(current);
            if (typeof renderConversationComposerCodexReasoningEffort === "function") renderConversationComposerCodexReasoningEffort(current);
            if (typeof renderConversationComposerCodeBuddyModel === "function") renderConversationComposerCodeBuddyModel(current);
            if (typeof renderConversationComposerClaudeModel === "function") renderConversationComposerClaudeModel(current);
          }
        })
        .catch(() => {
          const current = typeof currentConversationCtx === "function" ? currentConversationCtx() : null;
          if (current && String(current.sessionId || "").trim() === sid) {
            if (typeof renderConversationComposerCodexModel === "function") renderConversationComposerCodexModel(current);
            if (typeof renderConversationComposerCodexReasoningEffort === "function") renderConversationComposerCodexReasoningEffort(current);
            if (typeof renderConversationComposerCodeBuddyModel === "function") renderConversationComposerCodeBuddyModel(current);
            if (typeof renderConversationComposerClaudeModel === "function") renderConversationComposerClaudeModel(current);
          }
        });
    }

    function conversationComposerSessionModel(ctx) {
      const context = (ctx && typeof ctx === "object") ? ctx : null;
      const sid = String((context && context.sessionId) || STATE.selectedSessionId || "").trim();
      const session = sid && typeof findConversationSessionById === "function"
        ? findConversationSessionById(sid)
        : null;
      const cliType = conversationComposerCliType(context, session);
      const sessionCliType = conversationComposerCliType(null, session);
      const sessionModel = conversationComposerCliTypesMatch(cliType, sessionCliType)
        ? (session && session.model)
        : "";
      const cachedModel = conversationComposerCachedModelForCli(sid, cliType);
      const detailModel = (
        typeof isClaudeCliType === "function"
        && isClaudeCliType(cliType)
        && conversationComposerSessionDetailLoadedForModel(sid)
      )
        ? normalizeSessionModel(
          (PCONV.sessionDetailModelById && PCONV.sessionDetailModelById[sid])
          || sessionModel
        )
        : "";
      return normalizeSessionModel(firstNonEmptyText([
        detailModel,
        cachedModel,
        sessionModel,
        context && context.model,
      ]));
    }

    function conversationComposerSelectedModel(ctx, sessionModel = "") {
      const context = (ctx && typeof ctx === "object") ? ctx : null;
      const sid = String((context && context.sessionId) || STATE.selectedSessionId || "").trim();
      const cliType = conversationComposerCliType(context);
      const select = conversationComposerModelSelectForCli(cliType);
      if (!sid || !select || select.hidden) return "";
      if (String(select.dataset.sessionId || "").trim() !== sid) return "";
      if (select.dataset.saving === "1") return "";
      const saved = normalizeSessionModel(select.dataset.model);
      const selected = normalizeSessionModel(select.value);
      const canonicalSessionModel = normalizeSessionModel(sessionModel);
      if (!selected) return "";
      if (canonicalSessionModel && saved && saved !== canonicalSessionModel) return "";
      if (canonicalSessionModel && selected === canonicalSessionModel) return selected;
      if (saved && selected === saved) return selected;
      return "";
    }

    function resolveConversationComposerModel(ctx, opts = {}) {
      const context = (ctx && typeof ctx === "object")
        ? ctx
        : (currentConversationCtx() || resolveConversationSendCtx());
      const cliType = context ? conversationComposerCliType(context) : "";
      if (!context || !conversationComposerSupportsModelSwitch(cliType)) return "";
      const sessionModel = conversationComposerSessionModel(context);
      const selectedModel = opts.preferSelected === false
        ? ""
        : conversationComposerSelectedModel(context, sessionModel);
      const fallback = opts.includeDefault === false || !conversationComposerModelCanUseDefault(context, sessionModel)
        ? ""
        : conversationComposerDefaultModelForCli(cliType);
      return selectedModel || sessionModel || fallback;
    }

    function resolveConversationComposerPayloadModel(ctx) {
      const context = (ctx && typeof ctx === "object")
        ? ctx
        : (currentConversationCtx() || resolveConversationSendCtx());
      const cliType = context ? conversationComposerCliType(context) : "";
      if (!context || !conversationComposerSupportsModelSwitch(cliType)) return "";
      const sessionModel = conversationComposerSessionModel(context);
      const selectedModel = conversationComposerSelectedModel(context, sessionModel);
      if (isCodexCliType(cliType) || (typeof isClaudeCliType === "function" && isClaudeCliType(cliType))) {
        return selectedModel || sessionModel || (
          conversationComposerModelCanUseDefault(context, sessionModel)
            ? conversationComposerDefaultModelForCli(cliType)
            : ""
        );
      }
      return selectedModel || sessionModel || "";
    }

    function syncConversationComposerCodexSettingsToLocal(sessionId, patchRaw, projectId = "") {
      const sid = String(sessionId || "").trim();
      const patch = (patchRaw && typeof patchRaw === "object") ? patchRaw : {};
      const hasModel = Object.prototype.hasOwnProperty.call(patch, "model");
      const hasReasoningEffort = Object.prototype.hasOwnProperty.call(patch, "reasoning_effort")
        || Object.prototype.hasOwnProperty.call(patch, "reasoningEffort");
      const model = normalizeSessionModel(patch.model);
      const reasoningEffort = normalizeReasoningEffort(patch.reasoning_effort || patch.reasoningEffort);
      if (!sid || (!hasModel && !hasReasoningEffort)) return false;
      const pid = String(projectId || STATE.project || "").trim();
      if (hasModel) {
        if (!PCONV.codexModelBySessionId || typeof PCONV.codexModelBySessionId !== "object") {
          PCONV.codexModelBySessionId = Object.create(null);
        }
        PCONV.codexModelBySessionId[sid] = model;
      }
      if (hasReasoningEffort) {
        if (!PCONV.codexReasoningEffortBySessionId || typeof PCONV.codexReasoningEffortBySessionId !== "object") {
          PCONV.codexReasoningEffortBySessionId = Object.create(null);
        }
        PCONV.codexReasoningEffortBySessionId[sid] = reasoningEffort;
      }
      const patchRow = (row) => {
        if (!row || typeof row !== "object") return row;
        if (hasModel) {
          row.model = model;
          row.model_source = model ? "composer-model-switch" : "cli-default";
          row.modelSource = row.model_source;
        }
        if (hasReasoningEffort) {
          row.reasoning_effort = reasoningEffort;
          row.reasoningEffort = reasoningEffort;
          row.reasoning_effort_source = reasoningEffort ? "composer-reasoning-switch" : "cli-default";
          row.reasoningEffortSource = row.reasoning_effort_source;
        }
        if (!row.cli_type) row.cli_type = "codex";
        return row;
      };
      const updateList = (list) => {
        if (!Array.isArray(list)) return false;
        let changed = false;
        list.forEach((row) => {
          if (String(getSessionId(row) || "").trim() !== sid) return;
          patchRow(row);
          changed = true;
        });
        return changed;
      };
      let changed = updateList(PCONV.sessions);
      if (PCONV.sessionDirectoryByProject && typeof PCONV.sessionDirectoryByProject === "object") {
        const projectIds = pid && PCONV.sessionDirectoryByProject[pid]
          ? [pid]
          : Object.keys(PCONV.sessionDirectoryByProject);
        projectIds.forEach((itemProjectId) => {
          if (updateList(PCONV.sessionDirectoryByProject[itemProjectId])) changed = true;
        });
      }
      const sessionPatch = patchRow({
        id: sid,
        sessionId: sid,
        project_id: pid,
        cli_type: "codex",
        source: hasModel ? (model ? "composer-model-switch" : "cli-default") : (reasoningEffort ? "composer-reasoning-switch" : "cli-default"),
      });
      if (typeof mergeConversationSessionDetailIntoStore === "function") {
        mergeConversationSessionDetailIntoStore(sessionPatch, sid);
      }
      if (typeof conversationStoreUpsertSession === "function") {
        conversationStoreUpsertSession(sessionPatch, { projectId: pid, source: sessionPatch.source });
      }
      if (
        typeof SESSION_INFO_UI === "object"
        && SESSION_INFO_UI
        && SESSION_INFO_UI.open
        && String(SESSION_INFO_UI.sessionId || "").trim() === sid
      ) {
        SESSION_INFO_UI.base = patchRow({ ...(SESSION_INFO_UI.base || {}) });
        SESSION_INFO_UI.form = patchRow({ ...(SESSION_INFO_UI.form || {}) });
        if (typeof renderConversationSessionInfoModal === "function") renderConversationSessionInfoModal();
      }
      return changed;
    }

    function syncConversationComposerCodexModelToLocal(sessionId, model, projectId = "") {
      return syncConversationComposerCodexSettingsToLocal(sessionId, { model }, projectId);
    }

    function syncConversationComposerCodexReasoningEffortToLocal(sessionId, reasoningEffort, projectId = "") {
      return syncConversationComposerCodexSettingsToLocal(sessionId, { reasoning_effort: reasoningEffort }, projectId);
    }

    function hideConversationComposerCodexModel() {
      const control = document.getElementById("convCodexModelControl");
      const input = document.getElementById("convCodexModelInput");
      const status = document.getElementById("convCodexModelStatus");
      if (control) control.hidden = true;
      if (input) {
        input.value = "";
        input.disabled = false;
        input.dataset.sessionId = "";
        input.dataset.projectId = "";
        input.dataset.model = "";
        input.dataset.modelSource = "";
        input.dataset.saving = "";
      }
      if (status) status.textContent = "";
    }

    async function handleConversationComposerCodexModelChange() {
      const input = document.getElementById("convCodexModelInput");
      const status = document.getElementById("convCodexModelStatus");
      if (!input || input.dataset.saving === "1") return;
      const sid = String(input.dataset.sessionId || "").trim();
      const pid = String(input.dataset.projectId || STATE.project || "").trim();
      const previous = normalizeSessionModel(input.dataset.model);
      const next = normalizeSessionModel(input.value);
      if (!sid || next === previous) {
        input.value = next;
        return;
      }
      input.dataset.saving = "1";
      input.disabled = true;
      if (status) status.textContent = "保存中...";
      const ok = typeof tryUpdateSessionModel === "function"
        ? await tryUpdateSessionModel(sid, next)
        : false;
      if (!ok) {
        input.value = previous;
        input.dataset.saving = "";
        input.disabled = false;
        if (status) status.textContent = "保存失败，已回退";
        setHintText("conv", "Codex 模型切换失败，已回退原值。");
        return;
      }
      syncConversationComposerCodexModelToLocal(sid, next, pid);
      input.dataset.model = next;
      input.dataset.saving = "";
      input.disabled = false;
      const compatibilityHint = codexModelSelectionHint(next);
      if (status) status.textContent = next ? (compatibilityHint ? "已保存 · 注意兼容" : "已保存") : "已跟随 CLI";
      setHintText(
        "conv",
        next
          ? ("Codex 模型已切换为 " + codexModelDisplayName(next) + "，下一次发送将使用。" + (compatibilityHint ? (" " + compatibilityHint) : ""))
          : "已清除当前 session.model 覆盖，下一次发送将跟随 Codex CLI 默认模型。"
      );
      renderConversationComposerCodexModel(currentConversationCtx());
    }

    function renderConversationComposerCodexModel(ctx) {
      const control = document.getElementById("convCodexModelControl");
      const input = document.getElementById("convCodexModelInput");
      const datalist = document.getElementById("convCodexModelOptions");
      const status = document.getElementById("convCodexModelStatus");
      if (!control || !input) return;
      const context = (ctx && typeof ctx === "object") ? ctx : null;
      if (!context || !isCodexCliType(context.cliType)) {
        hideConversationComposerCodexModel();
        return;
      }
      const sessionModel = conversationComposerSessionModel(context);
      const readiness = conversationComposerModelReadiness(context, sessionModel);
      if (readiness && readiness.state !== "ready") {
        hydrateConversationComposerModelIfNeeded(context, sessionModel);
        control.hidden = false;
        control.title = "正在读取当前 session.model，完成前不显示界面默认值。";
        input.value = "";
        input.placeholder = readiness.state === "error" ? "模型配置读取失败" : "读取模型配置中...";
        input.dataset.sessionId = String(context.sessionId || "").trim();
        input.dataset.projectId = String(context.projectId || STATE.project || "").trim();
        input.dataset.model = "";
        input.dataset.modelSource = readiness.state;
        input.disabled = true;
        if (status && input.dataset.saving !== "1") status.textContent = readiness.statusText || "";
        return;
      }
      const selected = resolveConversationComposerModel(context, { preferSelected: false });
      control.hidden = false;
      control.title = "预设可直接选择，也可输入历史或自定义模型 ID；保存到当前 session.model。";
      populateCodexModelInput(input, datalist, selected, { allowEmpty: true });
      input.placeholder = modelInputPlaceholderByCli("codex");
      input.dataset.sessionId = String(context.sessionId || "").trim();
      input.dataset.projectId = String(context.projectId || STATE.project || "").trim();
      input.dataset.model = String(sessionModel || "");
      input.dataset.modelSource = sessionModel ? "session" : "cli-default";
      input.disabled = !!PCONV.sending || input.dataset.saving === "1";
      if (status && input.dataset.saving !== "1") status.textContent = codexModelSelectionHint(selected) ? "注意兼容" : "";
      if (!input.__codexComposerBound) {
        input.__codexComposerBound = true;
        input.addEventListener("change", handleConversationComposerCodexModelChange);
        input.addEventListener("keydown", (event) => {
          if (event.key !== "Enter") return;
          event.preventDefault();
          input.blur();
        });
      }
    }

    function conversationComposerSessionReasoningEffort(ctx) {
      const context = (ctx && typeof ctx === "object") ? ctx : null;
      const sid = String((context && context.sessionId) || STATE.selectedSessionId || "").trim();
      const session = sid && typeof findConversationSessionById === "function"
        ? findConversationSessionById(sid)
        : null;
      const cliType = conversationComposerCliType(context, session);
      const sessionCliType = conversationComposerCliType(null, session);
      const compatibleSession = conversationComposerCliTypesMatch(cliType, sessionCliType) ? session : null;
      const cached = sid && PCONV.codexReasoningEffortBySessionId
        ? PCONV.codexReasoningEffortBySessionId[sid]
        : "";
      return normalizeReasoningEffort(firstNonEmptyText([
        cached,
        compatibleSession && compatibleSession.reasoning_effort,
        compatibleSession && compatibleSession.reasoningEffort,
        context && context.reasoning_effort,
        context && context.reasoningEffort,
      ]));
    }

    function conversationComposerSelectedReasoningEffort(ctx, sessionEffort = "") {
      const context = (ctx && typeof ctx === "object") ? ctx : null;
      const sid = String((context && context.sessionId) || STATE.selectedSessionId || "").trim();
      const select = document.getElementById("convCodexReasoningSelect");
      if (!sid || !select || select.hidden || select.dataset.saving === "1") return "";
      if (String(select.dataset.sessionId || "").trim() !== sid) return "";
      const saved = normalizeReasoningEffort(select.dataset.reasoningEffort);
      const selected = normalizeReasoningEffort(select.value);
      const canonical = normalizeReasoningEffort(sessionEffort);
      if (!selected) return "";
      if (canonical && saved && saved !== canonical) return "";
      if (canonical && selected === canonical) return selected;
      if (saved && selected === saved) return selected;
      return "";
    }

    function resolveConversationComposerReasoningEffort(ctx) {
      const context = (ctx && typeof ctx === "object")
        ? ctx
        : (currentConversationCtx() || resolveConversationSendCtx());
      if (!context || !isCodexCliType(conversationComposerCliType(context))) return "";
      const sessionEffort = conversationComposerSessionReasoningEffort(context);
      const selected = conversationComposerSelectedReasoningEffort(context, sessionEffort);
      const fallback = conversationComposerModelCanUseDefault(context, sessionEffort)
        ? codexDefaultReasoningEffort()
        : "";
      return selected || sessionEffort || fallback;
    }

    function resolveConversationComposerReasoningPayload(ctx) {
      const effort = resolveConversationComposerReasoningEffort(ctx);
      return effort ? { reasoning_effort: effort } : {};
    }

    function hideConversationComposerCodexReasoningEffort() {
      const control = document.getElementById("convCodexReasoningControl");
      const select = document.getElementById("convCodexReasoningSelect");
      const status = document.getElementById("convCodexReasoningStatus");
      if (control) control.hidden = true;
      if (select) {
        select.value = "";
        select.disabled = false;
        select.dataset.sessionId = "";
        select.dataset.projectId = "";
        select.dataset.reasoningEffort = "";
        select.dataset.saving = "";
      }
      if (status) status.textContent = "";
    }

    async function handleConversationComposerCodexReasoningEffortChange() {
      const select = document.getElementById("convCodexReasoningSelect");
      const status = document.getElementById("convCodexReasoningStatus");
      if (!select || select.dataset.saving === "1") return;
      const sid = String(select.dataset.sessionId || "").trim();
      const pid = String(select.dataset.projectId || STATE.project || "").trim();
      const previous = normalizeReasoningEffort(select.dataset.reasoningEffort);
      const next = normalizeReasoningEffort(select.value);
      if (!sid || next === previous) {
        select.value = next;
        return;
      }
      select.dataset.saving = "1";
      select.disabled = true;
      if (status) status.textContent = "保存中...";
      const ok = typeof tryUpdateSessionReasoningEffort === "function"
        ? await tryUpdateSessionReasoningEffort(sid, next)
        : false;
      if (!ok) {
        select.value = previous;
        select.dataset.saving = "";
        select.disabled = false;
        if (status) status.textContent = "保存失败，已回退";
        setHintText("conv", "Codex 思考强度切换失败，已回退原值。");
        return;
      }
      syncConversationComposerCodexReasoningEffortToLocal(sid, next, pid);
      select.dataset.reasoningEffort = next;
      select.dataset.saving = "";
      select.disabled = false;
      if (status) status.textContent = next ? "已保存" : "已跟随 CLI";
      setHintText(
        "conv",
        next
          ? ("Codex 思考强度已切换为 " + codexReasoningEffortDisplayName(next) + "（" + next + "），下一次发送将使用。")
          : "已清除当前 session.reasoning_effort 覆盖，下一次发送将跟随 Codex CLI 默认配置。"
      );
      renderConversationComposerCodexReasoningEffort(currentConversationCtx());
    }

    function renderConversationComposerCodexReasoningEffort(ctx) {
      const control = document.getElementById("convCodexReasoningControl");
      const select = document.getElementById("convCodexReasoningSelect");
      const status = document.getElementById("convCodexReasoningStatus");
      if (!control || !select) return;
      const context = (ctx && typeof ctx === "object") ? ctx : null;
      if (!context || !isCodexCliType(context.cliType)) {
        hideConversationComposerCodexReasoningEffort();
        return;
      }
      const sessionEffort = conversationComposerSessionReasoningEffort(context);
      const readiness = conversationComposerModelReadiness(context, sessionEffort);
      if (readiness && readiness.state !== "ready") {
        hydrateConversationComposerModelIfNeeded(context, sessionEffort);
        control.hidden = false;
        renderConversationComposerModelLoadingOption(
          select,
          readiness.state === "error" ? "思考配置读取失败" : "读取思考配置中..."
        );
        select.dataset.sessionId = String(context.sessionId || "").trim();
        select.dataset.projectId = String(context.projectId || STATE.project || "").trim();
        select.dataset.reasoningEffort = "";
        select.disabled = true;
        if (status && select.dataset.saving !== "1") status.textContent = readiness.statusText || "";
        return;
      }
      const selected = resolveConversationComposerReasoningEffort(context);
      control.hidden = false;
      control.title = "留空跟随 Codex CLI 默认；也可选择轻度 / 中 / 高 / 极高并保存到当前 session.reasoning_effort。";
      populateCodexReasoningEffortSelect(select, selected, { allowEmpty: true });
      select.dataset.sessionId = String(context.sessionId || "").trim();
      select.dataset.projectId = String(context.projectId || STATE.project || "").trim();
      select.dataset.reasoningEffort = String(sessionEffort || "");
      select.disabled = !!PCONV.sending || select.dataset.saving === "1";
      if (status && select.dataset.saving !== "1") status.textContent = "";
      if (!select.__codexReasoningComposerBound) {
        select.__codexReasoningComposerBound = true;
        select.addEventListener("change", handleConversationComposerCodexReasoningEffortChange);
      }
    }

    function syncConversationComposerCodeBuddyModelToLocal(sessionId, model, projectId = "") {
      const sid = String(sessionId || "").trim();
      const normalized = normalizeSessionModel(model);
      if (!sid || !normalized) return false;
      const pid = String(projectId || STATE.project || "").trim();
      if (!PCONV.codeBuddyModelBySessionId || typeof PCONV.codeBuddyModelBySessionId !== "object") {
        PCONV.codeBuddyModelBySessionId = Object.create(null);
      }
      PCONV.codeBuddyModelBySessionId[sid] = normalized;
      const patchRow = (row) => {
        if (!row || typeof row !== "object") return row;
        row.model = normalized;
        row.model_source = "composer-model-switch";
        row.modelSource = "composer-model-switch";
        if (!row.cli_type) row.cli_type = "codebuddy";
        return row;
      };
      const updateList = (list) => {
        if (!Array.isArray(list)) return false;
        let changed = false;
        list.forEach((row) => {
          if (String(getSessionId(row) || "").trim() !== sid) return;
          patchRow(row);
          changed = true;
        });
        return changed;
      };
      let changed = updateList(PCONV.sessions);
      if (PCONV.sessionDirectoryByProject && typeof PCONV.sessionDirectoryByProject === "object") {
        const projectIds = pid && PCONV.sessionDirectoryByProject[pid]
          ? [pid]
          : Object.keys(PCONV.sessionDirectoryByProject);
        projectIds.forEach((itemProjectId) => {
          if (updateList(PCONV.sessionDirectoryByProject[itemProjectId])) changed = true;
        });
      }
      if (typeof mergeConversationSessionDetailIntoStore === "function") {
        mergeConversationSessionDetailIntoStore({
          id: sid,
          sessionId: sid,
          project_id: pid,
          cli_type: "codebuddy",
          model: normalized,
          source: "composer-model-switch",
          model_source: "composer-model-switch",
        }, sid);
      }
      if (typeof conversationStoreUpsertSession === "function") {
        conversationStoreUpsertSession({
          id: sid,
          sessionId: sid,
          project_id: pid,
          cli_type: "codebuddy",
          model: normalized,
          source: "composer-model-switch",
          model_source: "composer-model-switch",
        }, { projectId: pid, source: "composer-model-switch" });
      }
      if (
        typeof SESSION_INFO_UI === "object"
        && SESSION_INFO_UI
        && SESSION_INFO_UI.open
        && String(SESSION_INFO_UI.sessionId || "").trim() === sid
      ) {
        SESSION_INFO_UI.base = { ...(SESSION_INFO_UI.base || {}), model: normalized };
        SESSION_INFO_UI.form = { ...(SESSION_INFO_UI.form || {}), model: normalized };
        if (typeof renderConversationSessionInfoModal === "function") renderConversationSessionInfoModal();
      }
      return changed;
    }

    function hideConversationComposerCodeBuddyModel() {
      const control = document.getElementById("convCodeBuddyModelControl");
      const select = document.getElementById("convCodeBuddyModelSelect");
      const status = document.getElementById("convCodeBuddyModelStatus");
      if (control) control.hidden = true;
      if (select) {
        select.value = "";
        select.disabled = false;
        select.dataset.sessionId = "";
        select.dataset.projectId = "";
        select.dataset.model = "";
        select.dataset.modelSource = "";
      }
      if (status) status.textContent = "";
    }

    async function handleConversationComposerCodeBuddyModelChange() {
      const select = document.getElementById("convCodeBuddyModelSelect");
      const status = document.getElementById("convCodeBuddyModelStatus");
      if (!select || select.dataset.saving === "1") return;
      const sid = String(select.dataset.sessionId || "").trim();
      const pid = String(select.dataset.projectId || STATE.project || "").trim();
      const previous = normalizeSessionModel(select.dataset.model) || codeBuddyDefaultModel();
      const next = normalizeSessionModel(select.value) || codeBuddyDefaultModel();
      if (!sid || next === previous) {
        select.value = next;
        return;
      }
      select.dataset.saving = "1";
      select.disabled = true;
      if (status) status.textContent = "保存中...";
      const ok = typeof tryUpdateSessionModel === "function"
        ? await tryUpdateSessionModel(sid, next)
        : false;
      if (!ok) {
        select.value = previous;
        select.dataset.saving = "";
        select.disabled = false;
        if (status) status.textContent = "保存失败，已保留原值";
        setHintText("conv", "CodeBuddy 模型切换失败，已保留原值。");
        return;
      }
      syncConversationComposerCodeBuddyModelToLocal(sid, next, pid);
      select.dataset.model = next;
      select.dataset.saving = "";
      select.disabled = false;
      if (status) status.textContent = "下一次发送将使用";
      const displayName = typeof codeBuddyModelDisplayName === "function" ? codeBuddyModelDisplayName(next) : next;
      setHintText("conv", "CodeBuddy 模型已切换为 " + displayName + "，下一次发送将使用。");
      renderConversationComposerCodeBuddyModel(currentConversationCtx());
    }

    function renderConversationComposerCodeBuddyModel(ctx) {
      const control = document.getElementById("convCodeBuddyModelControl");
      const select = document.getElementById("convCodeBuddyModelSelect");
      const status = document.getElementById("convCodeBuddyModelStatus");
      if (!control || !select) return;
      const context = (ctx && typeof ctx === "object") ? ctx : null;
      if (!context || !isCodeBuddyCliType(context.cliType)) {
        hideConversationComposerCodeBuddyModel();
        return;
      }
      const sessionModel = conversationComposerSessionModel(context);
      const readiness = conversationComposerModelReadiness(context, sessionModel);
      if (readiness && readiness.state !== "ready") {
        hydrateConversationComposerModelIfNeeded(context, sessionModel);
        control.hidden = false;
        control.title = readiness.state === "error"
          ? "暂未读取到当前 session.model，避免误显示默认模型。"
          : "正在读取当前 session.model，读取完成前不显示默认模型。";
        renderConversationComposerModelLoadingOption(
          select,
          readiness.state === "error" ? "模型配置读取失败" : "读取模型配置中..."
        );
        select.dataset.sessionId = String(context.sessionId || "").trim();
        select.dataset.projectId = String(context.projectId || STATE.project || "").trim();
        select.dataset.model = "";
        select.dataset.modelSource = readiness.state;
        select.disabled = true;
        if (status && select.dataset.saving !== "1") status.textContent = readiness.statusText || "";
        return;
      }
      const selected = resolveConversationComposerModel(context, { preferSelected: false });
      control.hidden = false;
      control.title = "界面展示可读名，实际保存值为模型 ID；默认值仅为创建预设，可改选。";
      populateCodeBuddyModelSelect(select, selected);
      select.dataset.sessionId = String(context.sessionId || "").trim();
      select.dataset.projectId = String(context.projectId || STATE.project || "").trim();
      select.dataset.model = String(sessionModel || "");
      select.dataset.modelSource = sessionModel ? "session" : "default";
      select.disabled = !!PCONV.sending || select.dataset.saving === "1";
      if (status && select.dataset.saving !== "1") status.textContent = "";
      if (!select.__codeBuddyComposerBound) {
        select.__codeBuddyComposerBound = true;
        select.addEventListener("change", handleConversationComposerCodeBuddyModelChange);
      }
    }

    function syncConversationComposerClaudeModelToLocal(sessionId, model, projectId = "") {
      const sid = String(sessionId || "").trim();
      const normalized = normalizeSessionModel(model);
      if (!sid || !normalized) return false;
      const pid = String(projectId || STATE.project || "").trim();
      if (!PCONV.claudeModelBySessionId || typeof PCONV.claudeModelBySessionId !== "object") {
        PCONV.claudeModelBySessionId = Object.create(null);
      }
      PCONV.claudeModelBySessionId[sid] = normalized;
      if (!PCONV.sessionDetailModelById || typeof PCONV.sessionDetailModelById !== "object") {
        PCONV.sessionDetailModelById = Object.create(null);
      }
      PCONV.sessionDetailModelById[sid] = normalized;
      const patchRow = (row) => {
        if (!row || typeof row !== "object") return row;
        row.model = normalized;
        row.model_source = "composer-model-switch";
        row.modelSource = "composer-model-switch";
        if (!row.cli_type) row.cli_type = "claude";
        return row;
      };
      const updateList = (list) => {
        if (!Array.isArray(list)) return false;
        let changed = false;
        list.forEach((row) => {
          if (String(getSessionId(row) || "").trim() !== sid) return;
          patchRow(row);
          changed = true;
        });
        return changed;
      };
      let changed = updateList(PCONV.sessions);
      if (PCONV.sessionDirectoryByProject && typeof PCONV.sessionDirectoryByProject === "object") {
        const projectIds = pid && PCONV.sessionDirectoryByProject[pid]
          ? [pid]
          : Object.keys(PCONV.sessionDirectoryByProject);
        projectIds.forEach((itemProjectId) => {
          if (updateList(PCONV.sessionDirectoryByProject[itemProjectId])) changed = true;
        });
      }
      if (typeof mergeConversationSessionDetailIntoStore === "function") {
        mergeConversationSessionDetailIntoStore({
          id: sid,
          sessionId: sid,
          project_id: pid,
          cli_type: "claude",
          model: normalized,
          source: "composer-model-switch",
          model_source: "composer-model-switch",
        }, sid);
      }
      if (typeof conversationStoreUpsertSession === "function") {
        conversationStoreUpsertSession({
          id: sid,
          sessionId: sid,
          project_id: pid,
          cli_type: "claude",
          model: normalized,
          source: "composer-model-switch",
          model_source: "composer-model-switch",
        }, { projectId: pid, source: "composer-model-switch" });
      }
      if (
        typeof SESSION_INFO_UI === "object"
        && SESSION_INFO_UI
        && SESSION_INFO_UI.open
        && String(SESSION_INFO_UI.sessionId || "").trim() === sid
      ) {
        SESSION_INFO_UI.base = { ...(SESSION_INFO_UI.base || {}), model: normalized };
        SESSION_INFO_UI.form = { ...(SESSION_INFO_UI.form || {}), model: normalized };
        if (typeof renderConversationSessionInfoModal === "function") renderConversationSessionInfoModal();
      }
      return changed;
    }

    function hideConversationComposerClaudeModel() {
      const control = document.getElementById("convClaudeModelControl");
      const select = document.getElementById("convClaudeModelSelect");
      const status = document.getElementById("convClaudeModelStatus");
      if (control) control.hidden = true;
      if (select) {
        select.value = "";
        select.disabled = false;
        select.dataset.sessionId = "";
        select.dataset.projectId = "";
        select.dataset.model = "";
        select.dataset.modelSource = "";
        select.dataset.saving = "";
      }
      if (status) status.textContent = "";
    }

    async function handleConversationComposerClaudeModelChange() {
      const select = document.getElementById("convClaudeModelSelect");
      const status = document.getElementById("convClaudeModelStatus");
      if (!select || select.dataset.saving === "1") return;
      const sid = String(select.dataset.sessionId || "").trim();
      const pid = String(select.dataset.projectId || STATE.project || "").trim();
      const previous = normalizeSessionModel(select.dataset.model) || conversationComposerDefaultModelForCli("claude");
      const next = normalizeSessionModel(select.value) || conversationComposerDefaultModelForCli("claude");
      const canonical = typeof claudeCanonicalModelForSave === "function"
        ? claudeCanonicalModelForSave(next)
        : next;
      if (!sid || next === previous) {
        select.value = next;
        return;
      }
      select.dataset.saving = "1";
      select.disabled = true;
      if (status) status.textContent = "保存中...";
      const ok = typeof tryUpdateSessionModel === "function"
        ? await tryUpdateSessionModel(sid, next, { expectedModel: canonical })
        : false;
      if (!ok) {
        select.value = previous;
        select.dataset.saving = "";
        select.disabled = false;
        if (status) status.textContent = "保存失败，已保留原值";
        setHintText("conv", "ClaudeCode 模型切换失败，已保留原值。");
        return;
      }
      syncConversationComposerClaudeModelToLocal(sid, canonical, pid);
      select.dataset.model = canonical;
      select.value = canonical;
      select.dataset.saving = "";
      select.disabled = false;
      if (status) status.textContent = "下一次发送将使用";
      const displayName = typeof claudeModelDisplayName === "function" ? claudeModelDisplayName(canonical) : canonical;
      setHintText("conv", "ClaudeCode 模型已切换为 " + displayName + "，下一次发送将使用。");
      renderConversationComposerClaudeModel(currentConversationCtx());
    }

    function renderConversationComposerClaudeModel(ctx) {
      const control = document.getElementById("convClaudeModelControl");
      const select = document.getElementById("convClaudeModelSelect");
      const status = document.getElementById("convClaudeModelStatus");
      if (!control || !select) return;
      const context = (ctx && typeof ctx === "object") ? ctx : null;
      if (!context || !(typeof isClaudeCliType === "function" && isClaudeCliType(context.cliType))) {
        hideConversationComposerClaudeModel();
        return;
      }
      const sessionModel = conversationComposerSessionModel(context);
      const readiness = conversationComposerModelReadiness(context, sessionModel);
      if (readiness && readiness.state !== "ready") {
        hydrateConversationComposerModelIfNeeded(context, sessionModel);
        control.hidden = false;
        control.title = readiness.state === "error"
          ? "暂未读取到当前 session.model，避免误显示默认 ClaudeCode 模型。"
          : "正在读取当前 session.model，读取完成前不显示默认 ClaudeCode 模型。";
        renderConversationComposerModelLoadingOption(
          select,
          readiness.state === "error" ? "模型配置读取失败" : "读取模型配置中..."
        );
        select.dataset.sessionId = String(context.sessionId || "").trim();
        select.dataset.projectId = String(context.projectId || STATE.project || "").trim();
        select.dataset.model = "";
        select.dataset.modelSource = readiness.state;
        select.disabled = true;
        if (status && select.dataset.saving !== "1") status.textContent = readiness.statusText || "";
        return;
      }
      const selected = resolveConversationComposerModel(context, { preferSelected: false });
      control.hidden = false;
      control.title = "ClaudeCode 模型会保存到当前 session.model，下一次发送透传给 runner --model。";
      if (typeof populateClaudeModelSelect === "function") {
        populateClaudeModelSelect(select, selected);
      } else {
        select.value = selected || conversationComposerDefaultModelForCli("claude");
      }
      select.dataset.sessionId = String(context.sessionId || "").trim();
      select.dataset.projectId = String(context.projectId || STATE.project || "").trim();
      select.dataset.model = String(sessionModel || "");
      select.dataset.modelSource = sessionModel ? "session" : "default";
      select.disabled = !!PCONV.sending || select.dataset.saving === "1";
      if (status && select.dataset.saving !== "1") status.textContent = "";
      if (!select.__claudeComposerBound) {
        select.__claudeComposerBound = true;
        select.addEventListener("change", handleConversationComposerClaudeModelChange);
      }
    }

    function conversationComposerSessionPermissionMode(ctx) {
      const context = (ctx && typeof ctx === "object") ? ctx : null;
      const sid = String((context && context.sessionId) || STATE.selectedSessionId || "").trim();
      const session = sid && typeof findConversationSessionById === "function"
        ? findConversationSessionById(sid)
        : null;
      const cliType = firstNonEmptyText([
        context && context.cliType,
        context && context.cli_type,
        session && session.cli_type,
        session && session.cliType,
      ]);
      const hasCachedMode = sid
        && isCodeBuddyCliType(cliType)
        && PCONV.codeBuddyPermissionModeBySessionId
        && typeof PCONV.codeBuddyPermissionModeBySessionId === "object"
        && Object.prototype.hasOwnProperty.call(PCONV.codeBuddyPermissionModeBySessionId, sid);
      const cachedMode = hasCachedMode
        ? normalizeCodeBuddyPermissionMode(PCONV.codeBuddyPermissionModeBySessionId[sid])
        : "";
      const raw = firstNonEmptyText([
        cachedMode,
        session && session.codebuddy_permission_mode,
        session && session.codebuddyPermissionMode,
        context && context.codebuddy_permission_mode,
        context && context.codebuddyPermissionMode,
      ]);
      return typeof normalizeCodeBuddyPermissionMode === "function"
        ? normalizeCodeBuddyPermissionMode(raw)
        : String(raw || "default").trim();
    }

    function conversationComposerSelectedPermissionMode(ctx, sessionMode = "") {
      const context = (ctx && typeof ctx === "object") ? ctx : null;
      const sid = String((context && context.sessionId) || STATE.selectedSessionId || "").trim();
      const select = document.getElementById("convCodeBuddyPermissionSelect");
      if (!sid || !select || select.hidden) return "";
      if (String(select.dataset.sessionId || "").trim() !== sid) return "";
      if (select.dataset.saving === "1") return "";
      const saved = normalizeCodeBuddyPermissionMode(select.dataset.mode);
      const selected = normalizeCodeBuddyPermissionMode(select.value);
      const canonicalSessionMode = normalizeCodeBuddyPermissionMode(sessionMode);
      if (!selected) return "";
      if (canonicalSessionMode && saved && saved !== canonicalSessionMode) return "";
      if (canonicalSessionMode && selected === canonicalSessionMode) return selected;
      if (saved && selected === saved) return selected;
      return "";
    }

    function resolveConversationComposerCodeBuddyPermissionMode(ctx) {
      const context = (ctx && typeof ctx === "object")
        ? ctx
        : (currentConversationCtx() || resolveConversationSendCtx());
      if (!context || !isCodeBuddyCliType(context.cliType)) return "";
      const sessionMode = conversationComposerSessionPermissionMode(context);
      const selectedMode = conversationComposerSelectedPermissionMode(context, sessionMode);
      return selectedMode || sessionMode || (
        typeof codeBuddyDefaultPermissionMode === "function" ? codeBuddyDefaultPermissionMode() : "default"
      );
    }

    function syncConversationComposerCodeBuddyPermissionModeToLocal(sessionId, mode, projectId = "") {
      const sid = String(sessionId || "").trim();
      const normalized = typeof normalizeCodeBuddyPermissionMode === "function"
        ? normalizeCodeBuddyPermissionMode(mode)
        : String(mode || "default").trim();
      if (!sid || !normalized) return false;
      const pid = String(projectId || STATE.project || "").trim();
      if (!PCONV.codeBuddyPermissionModeBySessionId || typeof PCONV.codeBuddyPermissionModeBySessionId !== "object") {
        PCONV.codeBuddyPermissionModeBySessionId = Object.create(null);
      }
      PCONV.codeBuddyPermissionModeBySessionId[sid] = normalized;
      const patchRow = (row) => {
        if (!row || typeof row !== "object") return row;
        row.codebuddy_permission_mode = normalized;
        row.codebuddyPermissionMode = normalized;
        row.codebuddy_permission_mode_source = "composer-permission-switch";
        row.codebuddyPermissionModeSource = "composer-permission-switch";
        row._codebuddy_permission_mode_present = true;
        if (!row.cli_type) row.cli_type = "codebuddy";
        return row;
      };
      const updateList = (list) => {
        if (!Array.isArray(list)) return false;
        let changed = false;
        list.forEach((row) => {
          if (String(getSessionId(row) || "").trim() !== sid) return;
          patchRow(row);
          changed = true;
        });
        return changed;
      };
      let changed = updateList(PCONV.sessions);
      if (PCONV.sessionDirectoryByProject && typeof PCONV.sessionDirectoryByProject === "object") {
        const projectIds = pid && PCONV.sessionDirectoryByProject[pid]
          ? [pid]
          : Object.keys(PCONV.sessionDirectoryByProject);
        projectIds.forEach((itemProjectId) => {
          if (updateList(PCONV.sessionDirectoryByProject[itemProjectId])) changed = true;
        });
      }
      if (typeof mergeConversationSessionDetailIntoStore === "function") {
        mergeConversationSessionDetailIntoStore({
          id: sid,
          sessionId: sid,
          project_id: pid,
          cli_type: "codebuddy",
          codebuddy_permission_mode: normalized,
          codebuddyPermissionMode: normalized,
          codebuddy_permission_mode_source: "composer-permission-switch",
          codebuddyPermissionModeSource: "composer-permission-switch",
          _codebuddy_permission_mode_present: true,
          source: "composer-permission-switch",
        }, sid);
      }
      if (typeof conversationStoreUpsertSession === "function") {
        conversationStoreUpsertSession({
          id: sid,
          sessionId: sid,
          project_id: pid,
          cli_type: "codebuddy",
          codebuddy_permission_mode: normalized,
          codebuddyPermissionMode: normalized,
          codebuddy_permission_mode_source: "composer-permission-switch",
          codebuddyPermissionModeSource: "composer-permission-switch",
          _codebuddy_permission_mode_present: true,
          source: "composer-permission-switch",
        }, { projectId: pid, source: "composer-permission-switch" });
      }
      if (
        typeof SESSION_INFO_UI === "object"
        && SESSION_INFO_UI
        && SESSION_INFO_UI.open
        && String(SESSION_INFO_UI.sessionId || "").trim() === sid
      ) {
        SESSION_INFO_UI.base = { ...(SESSION_INFO_UI.base || {}), codebuddy_permission_mode: normalized };
        SESSION_INFO_UI.form = { ...(SESSION_INFO_UI.form || {}), codebuddy_permission_mode: normalized };
        if (typeof renderConversationSessionInfoModal === "function") renderConversationSessionInfoModal();
      }
      return changed;
    }

    function hideConversationComposerCodeBuddyPermissionMode() {
      const control = document.getElementById("convCodeBuddyPermissionControl");
      const select = document.getElementById("convCodeBuddyPermissionSelect");
      const status = document.getElementById("convCodeBuddyPermissionStatus");
      if (control) {
        control.hidden = true;
        control.classList.remove("is-danger");
      }
      if (select) {
        select.value = "";
        select.disabled = false;
        select.dataset.sessionId = "";
        select.dataset.projectId = "";
        select.dataset.mode = "";
        select.dataset.saving = "";
      }
      if (status) status.textContent = "";
    }

    async function handleConversationComposerCodeBuddyPermissionModeChange() {
      const control = document.getElementById("convCodeBuddyPermissionControl");
      const select = document.getElementById("convCodeBuddyPermissionSelect");
      const status = document.getElementById("convCodeBuddyPermissionStatus");
      if (!select || select.dataset.saving === "1") return;
      const sid = String(select.dataset.sessionId || "").trim();
      const pid = String(select.dataset.projectId || STATE.project || "").trim();
      const previous = typeof normalizeCodeBuddyPermissionMode === "function"
        ? normalizeCodeBuddyPermissionMode(select.dataset.mode)
        : String(select.dataset.mode || "default").trim();
      const next = typeof normalizeCodeBuddyPermissionMode === "function"
        ? normalizeCodeBuddyPermissionMode(select.value)
        : String(select.value || "default").trim();
      if (!sid || next === previous) {
        select.value = next;
        if (control) control.classList.toggle("is-danger", next === "bypassPermissions");
        if (status) status.textContent = next === "bypassPermissions" ? "高风险" : "";
        return;
      }
      select.dataset.saving = "1";
      select.disabled = true;
      if (status) status.textContent = "保存中...";
      const ok = typeof tryUpdateSessionCodeBuddyPermissionMode === "function"
        ? await tryUpdateSessionCodeBuddyPermissionMode(sid, next)
        : false;
      if (!ok) {
        select.value = previous;
        select.dataset.saving = "";
        select.disabled = false;
        if (control) control.classList.toggle("is-danger", previous === "bypassPermissions");
        if (status) status.textContent = "保存失败，已保留原值";
        setHintText("conv", "CodeBuddy 授权模式切换失败，已保留原值。");
        return;
      }
      syncConversationComposerCodeBuddyPermissionModeToLocal(sid, next, pid);
      select.dataset.mode = next;
      select.dataset.saving = "";
      select.disabled = false;
      if (control) control.classList.toggle("is-danger", next === "bypassPermissions");
      if (status) status.textContent = next === "bypassPermissions" ? "高风险" : "";
      const displayName = typeof codeBuddyPermissionModeDisplayName === "function"
        ? codeBuddyPermissionModeDisplayName(next)
        : next;
      const riskText = next === "bypassPermissions"
        ? "全部授权会绕过 CodeBuddy 权限确认，可能执行文件修改和命令。"
        : "默认授权已启用。";
      setHintText("conv", "CodeBuddy 授权模式已切换为 " + displayName + "。" + riskText);
      renderConversationComposerCodeBuddyPermissionMode(currentConversationCtx());
    }

    function renderConversationComposerCodeBuddyPermissionMode(ctx) {
      const control = document.getElementById("convCodeBuddyPermissionControl");
      const select = document.getElementById("convCodeBuddyPermissionSelect");
      const status = document.getElementById("convCodeBuddyPermissionStatus");
      if (!control || !select) return;
      const context = (ctx && typeof ctx === "object") ? ctx : null;
      if (!context || !isCodeBuddyCliType(context.cliType)) {
        hideConversationComposerCodeBuddyPermissionMode();
        return;
      }
      const selected = resolveConversationComposerCodeBuddyPermissionMode(context);
      control.hidden = false;
      control.title = selected === "bypassPermissions"
        ? "全部授权会绕过 CodeBuddy 权限确认，可能执行文件修改和命令。"
        : "默认授权：保留 CodeBuddy 权限确认。";
      if (typeof populateCodeBuddyPermissionModeSelect === "function") {
        populateCodeBuddyPermissionModeSelect(select, selected);
      } else {
        select.value = selected || "default";
      }
      control.classList.toggle("is-danger", select.value === "bypassPermissions");
      select.dataset.sessionId = String(context.sessionId || "").trim();
      select.dataset.projectId = String(context.projectId || STATE.project || "").trim();
      select.dataset.mode = String(select.value || selected || "default");
      select.disabled = !!PCONV.sending || select.dataset.saving === "1";
      if (status && select.dataset.saving !== "1") {
        status.textContent = select.value === "bypassPermissions" ? "高风险" : "";
      }
      if (!select.__codeBuddyPermissionComposerBound) {
        select.__codeBuddyPermissionComposerBound = true;
        select.addEventListener("change", handleConversationComposerCodeBuddyPermissionModeChange);
      }
    }

    function conversationComposerSessionClaudePermissionMode(ctx) {
      const context = (ctx && typeof ctx === "object") ? ctx : null;
      const sid = String((context && context.sessionId) || STATE.selectedSessionId || "").trim();
      const session = sid && typeof findConversationSessionById === "function"
        ? findConversationSessionById(sid)
        : null;
      const cliType = conversationComposerCliType(context, session);
      const hasCachedMode = sid
        && typeof isClaudeCliType === "function"
        && isClaudeCliType(cliType)
        && PCONV.claudePermissionModeBySessionId
        && typeof PCONV.claudePermissionModeBySessionId === "object"
        && Object.prototype.hasOwnProperty.call(PCONV.claudePermissionModeBySessionId, sid);
      const cachedMode = hasCachedMode
        ? normalizeClaudePermissionMode(PCONV.claudePermissionModeBySessionId[sid])
        : "";
      const raw = firstNonEmptyText([
        cachedMode,
        session && session.claude_permission_mode,
        session && session.claudePermissionMode,
        session && session.permission_mode,
        session && session.permissionMode,
        context && context.claude_permission_mode,
        context && context.claudePermissionMode,
        context && context.permission_mode,
        context && context.permissionMode,
      ]);
      return typeof normalizeClaudePermissionMode === "function"
        ? normalizeClaudePermissionMode(raw)
        : String(raw || "bypassPermissions").trim();
    }

    function conversationComposerSelectedClaudePermissionMode(ctx, sessionMode = "") {
      const context = (ctx && typeof ctx === "object") ? ctx : null;
      const sid = String((context && context.sessionId) || STATE.selectedSessionId || "").trim();
      const select = document.getElementById("convClaudePermissionSelect");
      if (!sid || !select || select.hidden) return "";
      if (String(select.dataset.sessionId || "").trim() !== sid) return "";
      if (select.dataset.saving === "1") return "";
      const saved = normalizeClaudePermissionMode(select.dataset.mode);
      const selected = normalizeClaudePermissionMode(select.value);
      const canonicalSessionMode = normalizeClaudePermissionMode(sessionMode);
      if (!selected) return "";
      if (canonicalSessionMode && saved && saved !== canonicalSessionMode) return "";
      if (canonicalSessionMode && selected === canonicalSessionMode) return selected;
      if (saved && selected === saved) return selected;
      return "";
    }

    function resolveConversationComposerClaudePermissionMode(ctx) {
      const context = (ctx && typeof ctx === "object")
        ? ctx
        : (currentConversationCtx() || resolveConversationSendCtx());
      if (!context || !(typeof isClaudeCliType === "function" && isClaudeCliType(context.cliType))) return "";
      const sessionMode = conversationComposerSessionClaudePermissionMode(context);
      const selectedMode = conversationComposerSelectedClaudePermissionMode(context, sessionMode);
      return selectedMode || sessionMode || (
        typeof claudeDefaultPermissionMode === "function" ? claudeDefaultPermissionMode() : "bypassPermissions"
      );
    }

    function resolveConversationComposerPermissionPayload(ctx) {
      const context = (ctx && typeof ctx === "object")
        ? ctx
        : (currentConversationCtx() || resolveConversationSendCtx());
      if (!context) return {};
      if (isCodeBuddyCliType(context.cliType)) {
        const mode = resolveConversationComposerCodeBuddyPermissionMode(context);
        return mode ? {
          codebuddy_permission_mode: mode,
          codebuddyPermissionMode: mode,
        } : {};
      }
      if (typeof isClaudeCliType === "function" && isClaudeCliType(context.cliType)) {
        const mode = resolveConversationComposerClaudePermissionMode(context);
        return mode ? {
          permission_mode: mode,
          permissionMode: mode,
          claude_permission_mode: mode,
          claudePermissionMode: mode,
        } : {};
      }
      return {};
    }

    function syncConversationComposerClaudePermissionModeToLocal(sessionId, mode, projectId = "") {
      const sid = String(sessionId || "").trim();
      const normalized = typeof normalizeClaudePermissionMode === "function"
        ? normalizeClaudePermissionMode(mode)
        : String(mode || "bypassPermissions").trim();
      if (!sid || !normalized) return false;
      const pid = String(projectId || STATE.project || "").trim();
      if (!PCONV.claudePermissionModeBySessionId || typeof PCONV.claudePermissionModeBySessionId !== "object") {
        PCONV.claudePermissionModeBySessionId = Object.create(null);
      }
      PCONV.claudePermissionModeBySessionId[sid] = normalized;
      const patchRow = (row) => {
        if (!row || typeof row !== "object") return row;
        row.claude_permission_mode = normalized;
        row.claudePermissionMode = normalized;
        row.permission_mode = normalized;
        row.permissionMode = normalized;
        row.claude_permission_mode_source = "composer-permission-switch";
        row.claudePermissionModeSource = "composer-permission-switch";
        if (!row.cli_type) row.cli_type = "claude";
        return row;
      };
      const updateList = (list) => {
        if (!Array.isArray(list)) return false;
        let changed = false;
        list.forEach((row) => {
          if (String(getSessionId(row) || "").trim() !== sid) return;
          patchRow(row);
          changed = true;
        });
        return changed;
      };
      let changed = updateList(PCONV.sessions);
      if (PCONV.sessionDirectoryByProject && typeof PCONV.sessionDirectoryByProject === "object") {
        const projectIds = pid && PCONV.sessionDirectoryByProject[pid]
          ? [pid]
          : Object.keys(PCONV.sessionDirectoryByProject);
        projectIds.forEach((itemProjectId) => {
          if (updateList(PCONV.sessionDirectoryByProject[itemProjectId])) changed = true;
        });
      }
      if (typeof mergeConversationSessionDetailIntoStore === "function") {
        mergeConversationSessionDetailIntoStore({
          id: sid,
          sessionId: sid,
          project_id: pid,
          cli_type: "claude",
          claude_permission_mode: normalized,
          claudePermissionMode: normalized,
          permission_mode: normalized,
          permissionMode: normalized,
          claude_permission_mode_source: "composer-permission-switch",
          claudePermissionModeSource: "composer-permission-switch",
          source: "composer-permission-switch",
        }, sid);
      }
      if (typeof conversationStoreUpsertSession === "function") {
        conversationStoreUpsertSession({
          id: sid,
          sessionId: sid,
          project_id: pid,
          cli_type: "claude",
          claude_permission_mode: normalized,
          claudePermissionMode: normalized,
          permission_mode: normalized,
          permissionMode: normalized,
          claude_permission_mode_source: "composer-permission-switch",
          claudePermissionModeSource: "composer-permission-switch",
          source: "composer-permission-switch",
        }, { projectId: pid, source: "composer-permission-switch" });
      }
      if (
        typeof SESSION_INFO_UI === "object"
        && SESSION_INFO_UI
        && SESSION_INFO_UI.open
        && String(SESSION_INFO_UI.sessionId || "").trim() === sid
      ) {
        SESSION_INFO_UI.base = { ...(SESSION_INFO_UI.base || {}), claude_permission_mode: normalized };
        SESSION_INFO_UI.form = { ...(SESSION_INFO_UI.form || {}), claude_permission_mode: normalized };
        if (typeof renderConversationSessionInfoModal === "function") renderConversationSessionInfoModal();
      }
      return changed;
    }

    function hideConversationComposerClaudePermissionMode() {
      const control = document.getElementById("convClaudePermissionControl");
      const select = document.getElementById("convClaudePermissionSelect");
      const status = document.getElementById("convClaudePermissionStatus");
      if (control) {
        control.hidden = true;
        control.classList.remove("is-danger");
      }
      if (select) {
        select.value = "";
        select.disabled = false;
        select.dataset.sessionId = "";
        select.dataset.projectId = "";
        select.dataset.mode = "";
        select.dataset.saving = "";
      }
      if (status) status.textContent = "";
    }

    async function handleConversationComposerClaudePermissionModeChange() {
      const control = document.getElementById("convClaudePermissionControl");
      const select = document.getElementById("convClaudePermissionSelect");
      const status = document.getElementById("convClaudePermissionStatus");
      if (!select || select.dataset.saving === "1") return;
      const sid = String(select.dataset.sessionId || "").trim();
      const pid = String(select.dataset.projectId || STATE.project || "").trim();
      const previous = typeof normalizeClaudePermissionMode === "function"
        ? normalizeClaudePermissionMode(select.dataset.mode)
        : String(select.dataset.mode || "bypassPermissions").trim();
      const next = typeof normalizeClaudePermissionMode === "function"
        ? normalizeClaudePermissionMode(select.value)
        : String(select.value || "bypassPermissions").trim();
      if (!sid || next === previous) {
        select.value = next;
        if (control) control.classList.toggle("is-danger", next === "bypassPermissions");
        if (status) status.textContent = next === "bypassPermissions" ? "高风险" : "";
        return;
      }
      select.dataset.saving = "1";
      select.disabled = true;
      if (status) status.textContent = "保存中...";
      const ok = typeof tryUpdateSessionClaudePermissionMode === "function"
        ? await tryUpdateSessionClaudePermissionMode(sid, next)
        : false;
      if (!ok) {
        select.value = previous;
        select.dataset.saving = "";
        select.disabled = false;
        if (control) control.classList.toggle("is-danger", previous === "bypassPermissions");
        if (status) status.textContent = "保存失败，已保留原值";
        setHintText("conv", "ClaudeCode 授权模式切换失败，已保留原值；可能需要后端先支持 Claude 授权字段回显。");
        return;
      }
      syncConversationComposerClaudePermissionModeToLocal(sid, next, pid);
      select.dataset.mode = next;
      select.dataset.saving = "";
      select.disabled = false;
      if (control) control.classList.toggle("is-danger", next === "bypassPermissions");
      if (status) status.textContent = next === "bypassPermissions" ? "高风险" : "";
      const displayName = typeof claudePermissionModeDisplayName === "function"
        ? claudePermissionModeDisplayName(next)
        : next;
      const riskText = next === "bypassPermissions"
        ? "最大授权会追加 --dangerously-skip-permissions，不会收紧当前默认体验。"
        : "已切换为更严格授权模式。";
      setHintText("conv", "ClaudeCode 授权模式已切换为 " + displayName + "。" + riskText);
      renderConversationComposerClaudePermissionMode(currentConversationCtx());
    }

    function renderConversationComposerClaudePermissionMode(ctx) {
      const control = document.getElementById("convClaudePermissionControl");
      const select = document.getElementById("convClaudePermissionSelect");
      const status = document.getElementById("convClaudePermissionStatus");
      if (!control || !select) return;
      const context = (ctx && typeof ctx === "object") ? ctx : null;
      if (!context || !(typeof isClaudeCliType === "function" && isClaudeCliType(context.cliType))) {
        hideConversationComposerClaudePermissionMode();
        return;
      }
      const selected = resolveConversationComposerClaudePermissionMode(context);
      control.hidden = false;
      control.title = selected === "bypassPermissions"
        ? "最大授权：发送时对应 --dangerously-skip-permissions。"
        : "更严格授权：default / acceptEdits / plan 会收紧 ClaudeCode 权限。";
      if (typeof populateClaudePermissionModeSelect === "function") {
        populateClaudePermissionModeSelect(select, selected);
      } else {
        select.value = selected || "bypassPermissions";
      }
      control.classList.toggle("is-danger", select.value === "bypassPermissions");
      select.dataset.sessionId = String(context.sessionId || "").trim();
      select.dataset.projectId = String(context.projectId || STATE.project || "").trim();
      select.dataset.mode = String(select.value || selected || "bypassPermissions");
      select.disabled = !!PCONV.sending || select.dataset.saving === "1";
      if (status && select.dataset.saving !== "1") {
        status.textContent = select.value === "bypassPermissions" ? "高风险" : "";
      }
      if (!select.__claudePermissionComposerBound) {
        select.__claudePermissionComposerBound = true;
        select.addEventListener("change", handleConversationComposerClaudePermissionModeChange);
      }
    }
