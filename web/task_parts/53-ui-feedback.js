    let TD_TOAST_SEQ = 0;

    function createToastNode(tag, attrs = {}) {
      const node = document.createElement(tag);
      for (const [key, value] of Object.entries(attrs)) {
        if (key === "class") node.className = String(value || "");
        else if (key === "text") node.textContent = String(value || "");
        else node.setAttribute(key, String(value || ""));
      }
      return node;
    }

    function ensureToastStack() {
      let host = document.getElementById("tdToastStack");
      if (host) return host;
      host = createToastNode("div", { class: "td-toast-stack", id: "tdToastStack", "aria-live": "polite" });
      document.body.appendChild(host);
      return host;
    }

    function toast(message, options = {}) {
      const text = String(message || "").trim();
      if (!text) return;
      const opts = (options && typeof options === "object") ? options : {};
      const tone = String(opts.tone || opts.type || "success").trim() || "success";
      const duration = Math.max(1200, Number(opts.duration) || 2200);
      const host = ensureToastStack();
      const toastId = "td-toast-" + (++TD_TOAST_SEQ);
      const node = createToastNode("div", {
        class: "td-toast " + (tone === "error" ? "error" : "success"),
        id: toastId,
        role: "status",
        text,
      });
      host.appendChild(node);
      requestAnimationFrame(() => {
        node.classList.add("show");
      });
      window.setTimeout(() => {
        node.classList.remove("show");
        window.setTimeout(() => {
          if (node.parentNode) node.parentNode.removeChild(node);
        }, 180);
      }, duration);
    }

    function upsertCreatedChannelIntoLocalState(payload) {
      const src = (payload && typeof payload === "object") ? payload : {};
      const projectId = String(src.projectId || "").trim();
      const channelName = String(src.channelName || "").trim();
      if (!projectId || !channelName || typeof projectById !== "function") return false;
      const project = projectById(projectId);
      if (!project) return false;
      const channelDesc = String(src.channelDesc || channelName).trim() || channelName;
      const framework = (src.framework && typeof src.framework === "object") ? src.framework : {};
      const cliType = String(framework.cliType || "codex").trim() || "codex";

      if (!Array.isArray(project.channels)) project.channels = [];
      const hasChannel = project.channels.some((row) => String((row && row.name) || "").trim() === channelName);
      if (!hasChannel) {
        project.channels.push({
          name: channelName,
          alias: "",
          session_id: "",
          desc: channelDesc,
          cli_type: cliType,
          model: "",
        });
      }
      return true;
    }

    function existingChannelNameInProject(projectId, channelName) {
      const pid = String(projectId || "").trim();
      const target = String(channelName || "").trim();
      if (!pid || !target || typeof unionChannelNames !== "function") return "";
      const hit = unionChannelNames(pid).find((name) => String(name || "").trim() === target);
      return String(hit || "").trim();
    }

    function validateNewChannelDuplicateConflict(form) {
      const data = (form && typeof form === "object") ? form : {};
      const projectId = String(data.projectId || "").trim();
      const channelName = typeof buildNewChannelName === "function"
        ? String(buildNewChannelName(data) || "").trim()
        : "";
      const existing = existingChannelNameInProject(projectId, channelName);
      if (!existing) return "";
      return "通道「" + existing + "」已存在，请调整通道编号或业务主题后重试。";
    }

    function normalizeNewChannelFailureInfo(mode, response, payload, form) {
      const normalizedMode = String(mode || "direct").trim() === "agent_assist" ? "agent_assist" : "direct";
      const respStatus = Number((response && response.status) || 0) || 0;
      const body = (payload && typeof payload === "object") ? payload : {};
      const rawMessage = String(body.message || body.error || "").trim();
      const createdChannelName = String(
        body.channelName
        || (typeof buildNewChannelName === "function" ? buildNewChannelName(form || {}) : "")
        || ""
      ).trim();
      const duplicateConflict = respStatus === 409 || /already exists/i.test(rawMessage);
      if (duplicateConflict) {
        const label = createdChannelName || "当前通道";
        return {
          message: "通道「" + label + "」已存在，请调整通道编号或业务主题后重试。",
          detail: null,
        };
      }
      const prefix = normalizedMode === "agent_assist" ? "创建/派发失败：" : "创建失败：";
      const finalMessage = prefix + (rawMessage || (respStatus ? ("HTTP " + respStatus) : "网络或服务异常"));
      if (respStatus > 0 && respStatus < 500) {
        return { message: finalMessage, detail: null };
      }
      return {
        message: finalMessage,
        detail: body && Object.keys(body).length ? body : null,
      };
    }

    function notifyNewChannelDirectSuccess(form, payload) {
      const createdChannelName = String((payload && payload.channelName) || (typeof buildNewChannelName === "function" ? buildNewChannelName(form) : "") || "").trim();
      let message = "已创建通道";
      if (createdChannelName) message += "「" + createdChannelName + "」";
      message += "。";
      toast(message, { tone: "success" });
    }

    function finalizeDirectNewChannelSuccess(form, payload) {
      upsertCreatedChannelIntoLocalState(payload);
      if (typeof rebuildDashboardAfterStatusChange === "function") rebuildDashboardAfterStatusChange();
      if (typeof setNewChannelCreateSubmitting === "function") setNewChannelCreateSubmitting(false);
      if (typeof closeNewChannelModal === "function") closeNewChannelModal(true);
      if (typeof render === "function") render();
      notifyNewChannelDirectSuccess(form, payload);
    }
