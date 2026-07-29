    // Shared CLI model, permission and reasoning option definitions.
    function normalizeCliTypeLabel(raw) {
      const t = String(raw || "").trim().toLowerCase();
      if (!t) return "CODEX";
      if (t === "claude") return "CLAUDE";
      if (t === "opencode") return "OPENCODE";
      if (t === "trae") return "TRAE";
      if (t === "codebuddy") return "CODEBUDDY";
      if (t === "codex") return "CODEX";
      return t.toUpperCase();
    }

    function normalizeCliTypeClass(raw) {
      const t = String(raw || "").trim().toLowerCase();
      if (t === "claude") return "claude";
      if (t === "opencode") return "opencode";
      if (t === "gemini") return "gemini";
      if (t === "trae") return "trae";
      if (t === "codebuddy") return "codebuddy";
      if (t === "codex") return "codex";
      return "other";
    }

    function conversationCliBadgeText(raw) {
      const t = String(raw || "").trim().toLowerCase();
      if (!t || t === "codex") return "Codex";
      if (t === "claude") return "ClaudeCode";
      if (t === "opencode") return "OpenCode";
      if (t === "gemini") return "Gemini";
      if (t === "trae") return "Trae";
      if (t === "codebuddy") return "CodeBuddy";
      return String(raw || "").trim() || "Codex";
    }

    function normalizeSessionModel(raw) {
      return String(raw || "").trim();
    }

    const CODEX_DEFAULT_MODEL = "";
    const CODEX_MODEL_OPTIONS = [
      "gpt-5.6-sol",
      "gpt-5.6-terra",
      "gpt-5.6-luna",
      "gpt-5.5",
      "gpt-5.4",
      "gpt-5.4-mini",
      "gpt-5.3-codex-spark",
    ];

    const CODEX_REASONING_EFFORT_DEFAULT = "";
    const CODEX_REASONING_EFFORT_OPTIONS = [
      { value: "low", label: "轻度" },
      { value: "medium", label: "中" },
      { value: "high", label: "高" },
      { value: "xhigh", label: "极高" },
    ];

    function isCodexCliType(raw) {
      return String(raw || "").trim().toLowerCase() === "codex";
    }

    function codexDefaultModel() {
      return CODEX_DEFAULT_MODEL;
    }

    function codexModelOptions() {
      return CODEX_MODEL_OPTIONS.slice();
    }

    function codexModelDisplayName(raw) {
      const model = normalizeSessionModel(raw);
      const labels = {
        "gpt-5.6-sol": "GPT-5.6 Sol",
        "gpt-5.6-terra": "GPT-5.6 Terra",
        "gpt-5.6-luna": "GPT-5.6 Luna",
        "gpt-5.5": "GPT-5.5",
        "gpt-5.4": "GPT-5.4",
        "gpt-5.4-mini": "GPT-5.4 Mini",
        "gpt-5.3-codex-spark": "GPT-5.3 Codex Spark（API 兼容受限）",
      };
      return labels[model] || model;
    }

    function codexModelOptionText(raw) {
      const model = normalizeSessionModel(raw);
      const displayName = codexModelDisplayName(model);
      return displayName && displayName !== model ? (displayName + " · " + model) : model;
    }

    function populateCodexModelInput(inputEl, datalistEl, selectedRaw, opts = {}) {
      const options = (opts && typeof opts === "object") ? opts : {};
      const selected = normalizeSessionModel(selectedRaw)
        || (options.allowEmpty ? "" : codexDefaultModel());
      if (datalistEl) {
        datalistEl.innerHTML = "";
        codexModelOptions().forEach((model) => {
          datalistEl.appendChild(el("option", { value: model, label: codexModelOptionText(model) }));
        });
      }
      if (inputEl) inputEl.value = selected;
      return selected;
    }

    function codexModelSelectionHint(raw) {
      const model = normalizeSessionModel(raw);
      if (!model) return "";
      if (model === "gpt-5.3-codex-spark") {
        return "该模型在本机目录中可见，但 API 账号兼容受限；允许保存，实际可用性以运行结果为准。";
      }
      if (!codexModelOptions().includes(model)) {
        return "当前为历史或自定义模型值，已保留；前端不会做白名单拦截。";
      }
      return "";
    }

    const CODEBUDDY_DEFAULT_MODEL = "deepseek-v4-pro";
    const CODEBUDDY_MODEL_OPTIONS = [
      "hy3",
      "glm-5.2",
      "glm-5.1",
      "glm-5.0",
      "glm-5.0-turbo",
      "glm-5v-turbo",
      "glm-4.7",
      "minimax-m3-pay",
      "minimax-m2.7",
      "kimi-k2.7",
      "kimi-k2.6",
      "deepseek-v4-pro",
      "deepseek-v4-flash",
      "deepseek-v3-2-volc",
    ];

    function isCodeBuddyCliType(raw) {
      return String(raw || "").trim().toLowerCase() === "codebuddy";
    }

    const CLAUDE_DEFAULT_MODEL = "claude-opus-5";
    const CLAUDE_LEGACY_OPUS_MODEL = "claude-opus-4-8";
    const CLAUDE_MODEL_OPTIONS = [
      "claude-opus-5",
      "claude-sonnet-4-6",
      "claude-haiku-4-5",
      "claude-fable-5",
      "default",
      "sonnet",
      "opus",
      "haiku",
      "best",
      "opusplan",
    ];

    function isClaudeCliType(raw) {
      const t = String(raw || "").trim().toLowerCase();
      return t === "claude" || t === "claudecode" || t === "claude_code" || t === "claude-code";
    }

    function codeBuddyDefaultModel() {
      return CODEBUDDY_DEFAULT_MODEL;
    }

    function codeBuddyModelOptions() {
      return CODEBUDDY_MODEL_OPTIONS.slice();
    }

    function codeBuddyModelDisplayName(raw) {
      const model = normalizeSessionModel(raw);
      const labels = {
        "hy3": "HY3",
        "glm-5.2": "GLM 5.2",
        "glm-5.1": "GLM 5.1",
        "glm-5.0": "GLM 5.0",
        "glm-5.0-turbo": "GLM 5.0 Turbo",
        "glm-5v-turbo": "GLM 5V Turbo",
        "glm-4.7": "GLM 4.7",
        "minimax-m3-pay": "MiniMax M3",
        "minimax-m2.7": "MiniMax M2.7",
        "kimi-k2.7": "Kimi K2.7",
        "kimi-k2.6": "Kimi K2.6",
        "deepseek-v4-pro": "DeepSeek V4 Pro",
        "deepseek-v4-flash": "DeepSeek V4 Flash",
        "deepseek-v3-2-volc": "DeepSeek V3.2 Volc",
      };
      return labels[model] || model;
    }

    function codeBuddyModelOptionText(raw) {
      const model = normalizeSessionModel(raw);
      const displayName = codeBuddyModelDisplayName(model);
      return displayName && displayName !== model ? (displayName + " · " + model) : model;
    }

    function populateCodeBuddyModelSelect(selectEl, selectedRaw) {
      if (!selectEl) return "";
      const selected = normalizeSessionModel(selectedRaw) || codeBuddyDefaultModel();
      selectEl.innerHTML = "";
      const known = new Set(codeBuddyModelOptions());
      codeBuddyModelOptions().forEach((model) => {
        selectEl.appendChild(el("option", { value: model, text: codeBuddyModelOptionText(model) }));
      });
      if (selected && !known.has(selected)) {
        selectEl.appendChild(el("option", {
          value: selected,
          text: "历史模型：" + selected + "（当前不在账号支持快照中，保留原值，可改选）",
        }));
      }
      selectEl.value = selected;
      return String(selectEl.value || selected || "");
    }

    function claudeDefaultModel() {
      return CLAUDE_DEFAULT_MODEL;
    }

    function claudeModelOptions() {
      return CLAUDE_MODEL_OPTIONS.slice();
    }

    function claudeCanonicalModelForSave(raw) {
      const model = normalizeSessionModel(raw).toLowerCase().replace(/ /g, "-");
      const supported = new Set([
        "claude-opus-5",
        "claude-fable-5",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
      ]);
      if (supported.has(model)) return model;
      const aliases = {
        "claude-opus-4-8": "claude-opus-5",
        "claude-opus-4-20250514": "claude-opus-5",
        "default": "claude-opus-5",
        "best": "claude-opus-5",
        "fable": "claude-fable-5",
        "fable5": "claude-fable-5",
        "fable-5": "claude-fable-5",
        "fable_5": "claude-fable-5",
        "claude-fable": "claude-fable-5",
        "claude-fable5": "claude-fable-5",
        "opus": "claude-opus-5",
        "opusplan": "claude-opus-5",
        "opus-plan": "claude-opus-5",
        "opus_plan": "claude-opus-5",
        "claude-opus": "claude-opus-5",
        "sonnet": "claude-sonnet-4-6",
        "claude-sonnet": "claude-sonnet-4-6",
        "claude-sonnet-4-20250514": "claude-sonnet-4-6",
        "haiku": "claude-haiku-4-5",
        "claude-haiku": "claude-haiku-4-5",
      };
      return aliases[model] || claudeDefaultModel();
    }

    function claudeModelMigrationStatusText(raw) {
      return normalizeSessionModel(raw) === CLAUDE_LEGACY_OPUS_MODEL
        ? "Claude Opus 4.8（待迁移 / 状态更新中）"
        : "";
    }

    function claudeModelDisplayName(raw) {
      const model = normalizeSessionModel(raw);
      const labels = {
        "claude-opus-5": "Claude Opus 5",
        "claude-opus-4-8": "Claude Opus 4.8（待迁移 / 状态更新中）",
        "claude-sonnet-4-6": "Claude Sonnet 4.6",
        "claude-haiku-4-5": "Claude Haiku 4.5",
        "claude-fable-5": "Claude Fable 5",
        "default": "Alias: default",
        "sonnet": "Alias: sonnet",
        "opus": "Alias: opus",
        "haiku": "Alias: haiku",
        "best": "Alias: best",
        "opusplan": "Alias: opusplan",
      };
      return labels[model] || model;
    }

    function claudeModelOptionText(raw) {
      const model = normalizeSessionModel(raw);
      const displayName = claudeModelDisplayName(model);
      return displayName && displayName !== model ? (displayName + " · " + model) : model;
    }

    function populateClaudeModelSelect(selectEl, selectedRaw) {
      if (!selectEl) return "";
      const selected = normalizeSessionModel(selectedRaw) || claudeDefaultModel();
      selectEl.innerHTML = "";
      const known = new Set(claudeModelOptions());
      claudeModelOptions().forEach((model) => {
        selectEl.appendChild(el("option", { value: model, text: claudeModelOptionText(model) }));
      });
      if (selected && !known.has(selected)) {
        const migrationText = claudeModelMigrationStatusText(selected);
        const attrs = {
          value: selected,
          text: migrationText
            ? (migrationText + " · " + selected)
            : ("历史模型：" + selected + "（当前不在账号支持快照中，保留原值，可改选）"),
        };
        if (migrationText) attrs.disabled = "disabled";
        selectEl.appendChild(el("option", attrs));
      }
      selectEl.value = selected;
      return String(selectEl.value || selected || "");
    }

    const CODEBUDDY_PERMISSION_MODE_DEFAULT = "default";
    const CODEBUDDY_PERMISSION_MODE_OPTIONS = [
      { value: "default", label: "默认授权" },
      { value: "bypassPermissions", label: "全部授权" },
    ];

    function normalizeCodeBuddyPermissionMode(raw) {
      const text = String(raw || "").trim();
      if (!text) return CODEBUDDY_PERMISSION_MODE_DEFAULT;
      if (text === "default" || text === "bypassPermissions") return text;
      const key = text.toLowerCase().replace(/[\s-]+/g, "_");
      if (key === "bypass_permissions" || key === "bypasspermissions") return "bypassPermissions";
      return CODEBUDDY_PERMISSION_MODE_DEFAULT;
    }

    function codeBuddyDefaultPermissionMode() {
      return CODEBUDDY_PERMISSION_MODE_DEFAULT;
    }

    function codeBuddyPermissionModeOptions() {
      return CODEBUDDY_PERMISSION_MODE_OPTIONS.map((opt) => ({ ...opt }));
    }

    function codeBuddyPermissionModeDisplayName(raw) {
      const mode = normalizeCodeBuddyPermissionMode(raw);
      const hit = CODEBUDDY_PERMISSION_MODE_OPTIONS.find((opt) => opt.value === mode);
      return hit ? hit.label : "默认授权";
    }

    function populateCodeBuddyPermissionModeSelect(selectEl, selectedRaw) {
      if (!selectEl) return "";
      const selected = normalizeCodeBuddyPermissionMode(selectedRaw);
      selectEl.innerHTML = "";
      codeBuddyPermissionModeOptions().forEach((opt) => {
        selectEl.appendChild(el("option", { value: opt.value, text: opt.label }));
      });
      selectEl.value = selected;
      return String(selectEl.value || selected || codeBuddyDefaultPermissionMode());
    }

    const CLAUDE_PERMISSION_MODE_DEFAULT = "bypassPermissions";
    const CLAUDE_PERMISSION_MODE_OPTIONS = [
      { value: "bypassPermissions", label: "最大授权" },
      { value: "default", label: "默认授权" },
      { value: "acceptEdits", label: "自动接受编辑" },
      { value: "plan", label: "计划模式" },
    ];

    function normalizeClaudePermissionMode(raw) {
      const text = String(raw || "").trim();
      if (!text) return CLAUDE_PERMISSION_MODE_DEFAULT;
      if (text === "default" || text === "acceptEdits" || text === "plan" || text === "bypassPermissions") return text;
      const key = text.toLowerCase().replace(/[\s-]+/g, "_");
      if (key === "accept_edits" || key === "acceptedits") return "acceptEdits";
      if (key === "bypass_permissions" || key === "bypasspermissions" || key === "dangerously_skip_permissions") return "bypassPermissions";
      if (key === "dangerouslyskippermissions" || key === "__dangerously_skip_permissions") return "bypassPermissions";
      if (key === "full" || key === "max" || key === "maximum") return "bypassPermissions";
      return CLAUDE_PERMISSION_MODE_DEFAULT;
    }

    function claudeDefaultPermissionMode() {
      return CLAUDE_PERMISSION_MODE_DEFAULT;
    }

    function claudePermissionModeOptions() {
      return CLAUDE_PERMISSION_MODE_OPTIONS.map((opt) => ({ ...opt }));
    }

    function claudePermissionModeDisplayName(raw) {
      const mode = normalizeClaudePermissionMode(raw);
      const hit = CLAUDE_PERMISSION_MODE_OPTIONS.find((opt) => opt.value === mode);
      return hit ? hit.label : "最大授权";
    }

    function populateClaudePermissionModeSelect(selectEl, selectedRaw) {
      if (!selectEl) return "";
      const selected = normalizeClaudePermissionMode(selectedRaw);
      selectEl.innerHTML = "";
      claudePermissionModeOptions().forEach((opt) => {
        selectEl.appendChild(el("option", { value: opt.value, text: opt.label }));
      });
      selectEl.value = selected;
      return String(selectEl.value || selected || claudeDefaultPermissionMode());
    }

    function normalizeReasoningEffort(raw) {
      let t = String(raw || "").trim().toLowerCase();
      if (!t) return "";
      if (t === "extra_high" || t === "very_high" || t === "ultra" || t === "extra") t = "xhigh";
      if (t === "low" || t === "medium" || t === "high" || t === "xhigh") return t;
      return "";
    }

    function codexDefaultReasoningEffort() {
      return CODEX_REASONING_EFFORT_DEFAULT;
    }

    function codexReasoningEffortOptions() {
      return CODEX_REASONING_EFFORT_OPTIONS.map((opt) => ({ ...opt }));
    }

    function codexReasoningEffortDisplayName(raw) {
      const effort = normalizeReasoningEffort(raw) || codexDefaultReasoningEffort();
      if (!effort) return "跟随 Codex CLI 默认";
      const hit = CODEX_REASONING_EFFORT_OPTIONS.find((opt) => opt.value === effort);
      return hit ? hit.label : effort;
    }

    function populateCodexReasoningEffortSelect(selectEl, selectedRaw, opts = {}) {
      if (!selectEl) return "";
      const options = (opts && typeof opts === "object") ? opts : {};
      const allowEmpty = !!options.allowEmpty;
      const selected = normalizeReasoningEffort(selectedRaw)
        || (allowEmpty ? "" : codexDefaultReasoningEffort());
      selectEl.innerHTML = "";
      if (allowEmpty) {
        selectEl.appendChild(el("option", { value: "", text: "跟随 Codex CLI 默认" }));
      }
      codexReasoningEffortOptions().forEach((opt) => {
        selectEl.appendChild(el("option", { value: opt.value, text: opt.label + " · " + opt.value }));
      });
      selectEl.value = selected;
      return String(selectEl.value || selected || "");
    }

    function sessionModelLabel(raw) {
      const model = normalizeSessionModel(raw);
      return model || "默认模型";
    }

    function modelInputPlaceholderByCli(cliTypeRaw) {
      const t = String(cliTypeRaw || "").trim().toLowerCase();
      if (t === "codex") return "留空跟随 Codex CLI 默认；可选预设或输入自定义模型 ID";
      if (t === "claude") return "默认 claude-opus-5；可选完整模型 ID 或 alias";
      if (t === "gemini") return "例如：gemini-2.0-flash（可选，留空默认）";
      if (t === "opencode") return "可选模型标识（留空使用默认模型）";
      if (t === "trae") return "例如：gpt-4.1（需配置 TRAE_CONFIG_FILE）";
      if (t === "codebuddy") return "默认 deepseek-v4-pro 仅为创建预设，可改选；实际保存模型 ID";
      return "留空使用该 CLI 默认模型";
    }
