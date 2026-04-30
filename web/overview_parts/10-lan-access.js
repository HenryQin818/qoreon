    const LAN_ACCESS = {
      open: false,
      loading: false,
      saving: false,
      error: "",
      message: "",
      messageTone: "",
      state: null,
    };

    function lanAccessText(value) {
      return String(value == null ? "" : value).trim();
    }

    function lanAccessBool(value) {
      return value === true || value === "true" || value === 1 || value === "1";
    }

    function lanAccessUrl(state) {
      const row = (state && typeof state === "object") ? state : {};
      return firstNonEmptyText([
        row.lan && row.lan.url,
        row.origins && row.origins.lanUrl,
        row.origins && row.origins.publicOrigin,
      ], "");
    }

    function normalizeLanAccessState(payload) {
      const row = (payload && typeof payload === "object") ? payload : {};
      const listen = (row.listen && typeof row.listen === "object") ? row.listen : {};
      const frontEndAction = (row.frontEndAction && typeof row.frontEndAction === "object")
        ? row.frontEndAction
        : {};
      const enabled = lanAccessBool(row.enabled);
      const effectiveEnabled = lanAccessBool(row.effectiveEnabled);
      const requiresRestart = lanAccessBool(row.requiresRestart || row.requires_restart || listen.requiresRestart || frontEndAction.showRequiresRestart);
      const url = lanAccessUrl(row);
      return {
        raw: row,
        enabled,
        effectiveEnabled,
        requiresRestart,
        restartHint: lanAccessText(frontEndAction.restartHint) || (requiresRestart ? "重启 task-dashboard 服务后监听地址才会切换。" : ""),
        url,
        currentBind: lanAccessText(listen.currentBind),
        desiredBind: lanAccessText(listen.desiredBind),
      };
    }

    function lanAccessStatusMeta(state) {
      if (LAN_ACCESS.loading && !state) return { label: "读取中", className: "" };
      if (LAN_ACCESS.error) return { label: "异常", className: "is-error" };
      if (!state) return { label: "未知", className: "" };
      if (state.requiresRestart) return { label: "待重启", className: "is-pending" };
      if (state.effectiveEnabled) return { label: "已开启", className: "is-on" };
      return { label: "已关闭", className: "" };
    }

    function lanAccessSummaryText(state) {
      if (LAN_ACCESS.error) return "读取失败：" + LAN_ACCESS.error;
      if (LAN_ACCESS.loading && !state) return "正在读取当前运行状态...";
      if (!state) return "暂未读取到运行状态。";
      if (state.requiresRestart) {
        return state.enabled
          ? "已写入开启配置，重启服务后才会对局域网生效。"
          : "已写入关闭配置，重启服务后才会恢复本机访问。";
      }
      if (state.effectiveEnabled) return "当前服务已对可信局域网开放完整平台访问。";
      return "当前仅本机访问，局域网完整访问未开启。";
    }

    function setLanAccessMessage(text = "", tone = "") {
      LAN_ACCESS.message = lanAccessText(text);
      LAN_ACCESS.messageTone = lanAccessText(tone);
      renderLanAccessState();
    }

    async function copyLanAccessText(text) {
      const value = lanAccessText(text);
      if (!value) return false;
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(value);
          return true;
        }
      } catch (_) {}
      const ta = document.createElement("textarea");
      ta.value = value;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      let ok = false;
      try { ok = document.execCommand("copy"); } catch (_) { ok = false; }
      ta.remove();
      return ok;
    }

    function setLanAccessOpen(open) {
      LAN_ACCESS.open = !!open;
      const wrap = document.getElementById("lanAccessWrap");
      const pop = document.getElementById("lanAccessPop");
      const btn = document.getElementById("lanAccessBtn");
      if (wrap) wrap.classList.toggle("show", LAN_ACCESS.open);
      if (pop) pop.hidden = !LAN_ACCESS.open;
      if (btn) btn.setAttribute("aria-expanded", LAN_ACCESS.open ? "true" : "false");
      if (LAN_ACCESS.open && !LAN_ACCESS.state && !LAN_ACCESS.loading) {
        loadLanAccessState();
      }
    }

    function renderLanAccessState() {
      const state = LAN_ACCESS.state;
      const meta = lanAccessStatusMeta(state);
      const btn = document.getElementById("lanAccessBtn");
      const badge = document.getElementById("lanAccessBadge");
      const pill = document.getElementById("lanAccessStatusPill");
      const summary = document.getElementById("lanAccessSummary");
      const sw = document.getElementById("lanAccessSwitch");
      const switchText = document.getElementById("lanAccessSwitchText");
      const urlRow = document.getElementById("lanAccessUrlRow");
      const urlEl = document.getElementById("lanAccessUrl");
      const copyBtn = document.getElementById("lanAccessCopyBtn");
      const hint = document.getElementById("lanAccessHint");
      const restart = document.getElementById("lanAccessRestart");
      const refreshBtn = document.getElementById("lanAccessRefreshBtn");
      const msg = document.getElementById("lanAccessMessage");

      if (btn) {
        btn.classList.toggle("is-on", !!(state && state.effectiveEnabled && !state.requiresRestart));
        btn.classList.toggle("is-pending", !!(state && state.requiresRestart));
        btn.title = lanAccessSummaryText(state);
      }
      if (badge) badge.textContent = meta.label;
      if (pill) {
        pill.className = "lan-access-pill" + (meta.className ? (" " + meta.className) : "");
        pill.textContent = meta.label;
      }
      if (summary) summary.textContent = lanAccessSummaryText(state);
      if (sw) {
        sw.checked = !!(state && state.enabled);
        sw.disabled = !!(LAN_ACCESS.loading || LAN_ACCESS.saving);
      }
      if (switchText) {
        switchText.textContent = state && state.enabled
          ? "允许局域网访问完整平台"
          : "仅允许本机访问";
      }
      const showUrl = !!(state && state.enabled && state.url);
      if (urlRow) urlRow.hidden = !showUrl;
      if (urlEl) {
        urlEl.textContent = showUrl ? state.url : "-";
        urlEl.title = showUrl ? state.url : "";
      }
      if (copyBtn) copyBtn.disabled = !showUrl || LAN_ACCESS.loading || LAN_ACCESS.saving;
      if (hint) {
        if (showUrl) {
          hint.textContent = state.effectiveEnabled
            ? "复制后可在同一可信局域网设备访问。"
            : "地址已生成，但当前监听尚未生效，请先重启服务。";
        } else {
          hint.textContent = "关闭状态下不展示局域网地址。";
        }
      }
      if (restart) {
        restart.hidden = !(state && state.requiresRestart);
        restart.textContent = state && state.requiresRestart
          ? (state.restartHint || "重启 task-dashboard 服务后监听地址才会切换。")
          : "";
      }
      if (refreshBtn) refreshBtn.disabled = !!(LAN_ACCESS.loading || LAN_ACCESS.saving);
      if (msg) {
        msg.className = "lan-access-message" + (LAN_ACCESS.messageTone ? (" " + LAN_ACCESS.messageTone) : "");
        msg.textContent = LAN_ACCESS.message;
      }
    }

    async function loadLanAccessState() {
      LAN_ACCESS.loading = true;
      LAN_ACCESS.error = "";
      LAN_ACCESS.message = LAN_ACCESS.message || "";
      renderLanAccessState();
      try {
        const payload = await fetchJson("/api/runtime/lan-access", { cache: "no-store" });
        LAN_ACCESS.state = normalizeLanAccessState(payload);
        LAN_ACCESS.error = "";
      } catch (err) {
        LAN_ACCESS.error = lanAccessText(err && err.message ? err.message : err) || "读取失败";
      } finally {
        LAN_ACCESS.loading = false;
        renderLanAccessState();
      }
    }

    async function updateLanAccessEnabled(enabled) {
      if (LAN_ACCESS.saving) return;
      LAN_ACCESS.saving = true;
      LAN_ACCESS.error = "";
      setLanAccessMessage(enabled ? "正在写入开启配置..." : "正在写入关闭配置...");
      try {
        const payload = await fetchJson("/api/runtime/lan-access", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled: !!enabled }),
        });
        LAN_ACCESS.state = normalizeLanAccessState(payload);
        LAN_ACCESS.error = "";
        const state = LAN_ACCESS.state;
        if (state.requiresRestart) {
          setLanAccessMessage("配置已保存；重启 task-dashboard 服务后生效。", "ok");
        } else {
          setLanAccessMessage(state.effectiveEnabled ? "局域网访问已开启。" : "局域网访问已关闭。", "ok");
        }
      } catch (err) {
        LAN_ACCESS.error = lanAccessText(err && err.message ? err.message : err) || "保存失败";
        setLanAccessMessage("保存失败：" + LAN_ACCESS.error, "err");
      } finally {
        LAN_ACCESS.saving = false;
        renderLanAccessState();
      }
    }

    function initLanAccessEntry() {
      const wrap = document.getElementById("lanAccessWrap");
      const btn = document.getElementById("lanAccessBtn");
      const pop = document.getElementById("lanAccessPop");
      const sw = document.getElementById("lanAccessSwitch");
      const copyBtn = document.getElementById("lanAccessCopyBtn");
      const refreshBtn = document.getElementById("lanAccessRefreshBtn");
      if (!wrap || !btn || !pop || wrap.__lanAccessBound) return;
      wrap.__lanAccessBound = true;
      btn.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        setLanAccessOpen(!LAN_ACCESS.open);
      });
      pop.addEventListener("click", (event) => event.stopPropagation());
      if (sw) {
        sw.addEventListener("change", () => updateLanAccessEnabled(sw.checked));
      }
      if (copyBtn) {
        copyBtn.addEventListener("click", async () => {
          const ok = await copyLanAccessText(LAN_ACCESS.state && LAN_ACCESS.state.url);
          setLanAccessMessage(ok ? "LAN 地址已复制。" : "复制失败，请手动复制。", ok ? "ok" : "err");
        });
      }
      if (refreshBtn) refreshBtn.addEventListener("click", loadLanAccessState);
      document.addEventListener("click", (event) => {
        if (!LAN_ACCESS.open) return;
        if (wrap.contains(event.target)) return;
        setLanAccessOpen(false);
      });
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && LAN_ACCESS.open) setLanAccessOpen(false);
      });
      renderLanAccessState();
      loadLanAccessState();
    }

    initLanAccessEntry();
