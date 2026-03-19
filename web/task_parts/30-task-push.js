    // task.js 第三刀：任务详情/协作消息派发链路
    function findItemByPath(path) {
      const p = String(path || "").trim();
      if (!p) return null;
      return allItems().find((x) => String(x.path || "") === p) || null;
    }

    function openTaskPushModalByItem(it) {
      if (!it || !isTaskItem(it)) return;
      TASK_PUSH_MODAL.open = true;
      TASK_PUSH_MODAL.taskPath = String(it.path || "");
      renderTaskPushModal();
    }

    function closeTaskPushModal() {
      TASK_PUSH_MODAL.open = false;
      TASK_PUSH_MODAL.taskPath = "";
      renderTaskPushModal();
    }

    function taskPushModalItem() {
      return findItemByPath(TASK_PUSH_MODAL.taskPath);
    }

    function renderTaskPushModal() {
      const mask = document.getElementById("taskPushMask");
      const body = document.getElementById("taskPushModalBody");
      const sub = document.getElementById("taskPushModalSub");
      if (!mask || !body) return;
      if (!TASK_PUSH_MODAL.open) {
        mask.classList.remove("show");
        body.innerHTML = "";
        if (sub) sub.textContent = "统一协作消息派发入口（立即/定时）";
        return;
      }
      const it = taskPushModalItem();
      mask.classList.add("show");
      body.innerHTML = "";
      if (!it) {
        body.appendChild(el("div", { class: "hint", text: "任务不存在或已被移动，请关闭后重试。" }));
        return;
      }
      if (sub) sub.textContent = shortTitle(it.title || "任务");
      const card = renderTaskPushCard(it, { force: true });
      if (card) body.appendChild(card);
      else body.appendChild(el("div", { class: "hint", text: "当前任务暂不支持协作消息派发。" }));
    }

    function createTaskPushEntryBtn(it, compact = false) {
      if (!isTaskItem(it)) return null;
      const btn = el("button", {
        class: "btn taskpush-entry-btn" + (compact ? " compact" : ""),
        text: "协作派发",
        type: "button",
      });
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        openTaskPushModalByItem(it);
      });
      return btn;
    }

    function renderTaskAutoKickoffCard(it) {
      if (!it || !isTaskItem(it)) return null;
      const bucket = bucketKeyForStatus(it.status);
      if (bucket !== "进行中" && bucket !== "督办") return null;
      const state = taskAutoKickoffStateForTask(it);
      const st = state.status || {};
      const actionBusy = taskPushActionBusy(it);

      const card = el("section", { class: "task-kickoff-card" });
      const head = el("div", { class: "task-kickoff-head" });
      const title = el("div", { class: "task-kickoff-title" });
      title.appendChild(el("span", { text: "自动派发状态" }));
      title.appendChild(chip(state.label, state.tone));
      head.appendChild(title);

      const ops = el("div", { class: "task-kickoff-ops" });
      const refreshBtn = el("button", { class: "btn", text: "刷新状态" });
      refreshBtn.disabled = !!actionBusy;
      refreshBtn.addEventListener("click", () => {
        setTaskPushNote(it, "正在刷新自动派发状态…");
        maybeRerenderTaskDetail(it);
        ensureTaskPushStateForTask(it, { force: true });
      });
      ops.appendChild(refreshBtn);
      if (state.allowTakeover) {
        const takeoverBtn = el("button", { class: "btn primary", text: actionBusy === "send-now" ? "派发中..." : "手动派发一次" });
        takeoverBtn.disabled = !!actionBusy;
        takeoverBtn.addEventListener("click", () => {
          if (!String(getTaskPushDraft(it) || "").trim()) {
            setTaskPushDraft(it, taskPushDefaultMessage(it));
          }
          taskPushSendNow(it);
        });
        ops.appendChild(takeoverBtn);
      }
      head.appendChild(ops);
      card.appendChild(head);
      card.appendChild(el("div", { class: "task-kickoff-desc", text: state.desc }));

      const meta = el("div", { class: "task-kickoff-meta" });
      const add = (k, v, cls = "") => {
        const row = el("div", { class: "task-kickoff-meta-row" + (cls ? (" " + cls) : "") });
        row.appendChild(el("span", { class: "k", text: k }));
        row.appendChild(el("span", { class: "v", text: String(v || "-") }));
        meta.appendChild(row);
      };
      add("执行模式", taskPushModeLabel(st.mode));
      add("job_id", st.job_id || "-", "mono");
      add("run_id", st.last_run_id || "-", "mono");
      add("dispatch_state", taskPushDisplayStatusLabel(state.latest));
      if (st.updated_at || st.created_at) add("更新时间", formatTsOrDash(st.updated_at || st.created_at));
      if (st.last_error) add("错误", st.last_error, "error");
      card.appendChild(meta);
      return card;
    }

    function taskPushModeLabel(mode) {
      const m = String(mode || "").trim().toLowerCase();
      if (m === "immediate") return "立即";
      if (m === "scheduled") return "定时";
      return m || "-";
    }

    function taskPushAttemptResultLabel(result) {
      const r = String(result || "").trim().toLowerCase();
      return ({
        skipped_active: "目标会话活跃，跳过",
        dispatched: "已派发",
        dispatch_error: "派发失败",
      })[r] || (r || "-");
    }

    function taskPushTargetSessionRow(it) {
      const target = taskPushTargetForTask(it);
      if (!target.ok) return null;
      return sessionForChannel(target.projectId, target.channelName) || null;
    }

    function taskPushOwnerAgentMeta(it) {
      const target = taskPushTargetForTask(it);
      const sess = taskPushTargetSessionRow(it) || {};
      const agentName = firstNonEmptyText([
        sess.displayName,
        sess.alias,
        sess.displayChannel,
        sess.codexTitle,
        target.channelName,
      ], target.channelName || "目标Agent");
      const agentAlias = firstNonEmptyText([
        sess.alias,
        sess.displayName,
        sess.displayChannel,
        sess.codexTitle,
        agentName,
      ], agentName);
      return {
        channelName: String(target.channelName || "").trim(),
        sessionId: String(target.sessionId || sess.sessionId || "").trim(),
        agentName: String(agentName || "").trim(),
        alias: String(agentAlias || "").trim(),
        role: taskPushSessionRoleCode(sess),
        session: sess,
      };
    }

    function taskPushSessionRoleCode(sess) {
      const role = String(
        sess && (sess.session_role || sess.sessionRole || (sess.is_primary ? "primary" : ""))
      ).trim().toLowerCase();
      if (role === "primary") return "primary";
      if (role === "child") return "child";
      return "none";
    }

    function taskPushSessionRoleLabel(role) {
      if (role === "primary") return "主";
      if (role === "child") return "子";
      if (role === "none") return "none";
      return "-";
    }

    function taskPushCurrentBindingStateLabel(it) {
      const sess = taskPushTargetSessionRow(it);
      if (!sess) return "未完全绑定";
      const status = resolveConversationContextStatus(sess);
      return String((status && status.label) || "未完全绑定").trim() || "未完全绑定";
    }

    function taskPushProjectExecutionContextLine(it) {
      const sess = taskPushTargetSessionRow(it);
      const execMeta = buildProjectExecutionContextMeta(
        sess && (sess.project_execution_context || sess.projectExecutionContext || null)
      );
      const source = String((execMeta && execMeta.context_source) || "").trim().toLowerCase() || "unknown";
      return "project_execution_context: source=" + source + "; binding_state=" + taskPushCurrentBindingStateLabel(it);
    }

    function taskPushCurrentSessionLine(it) {
      const owner = taskPushOwnerAgentMeta(it);
      return "[当前会话: session_id=" + (owner.sessionId || "none") + "; binding_state=active]";
    }

    function taskPushSourceRefPayload(it) {
      const target = taskPushTargetForTask(it);
      const owner = taskPushOwnerAgentMeta(it);
      return {
        project_id: String(target.projectId || STATE.project || "").trim(),
        channel_name: String(taskPushSourceChannelName(it) || owner.channelName || "none").trim(),
        session_id: "none",
        run_id: "none",
      };
    }

    function taskPushCallbackPayload(it) {
      const sourceChannel = String(taskPushSourceChannelName(it) || "").trim();
      const out = {
        channel_name: sourceChannel || "none",
        session_id: "none",
      };
      if (!sourceChannel) delete out.channel_name;
      return out;
    }

    function taskPushOwnerRefPayload(it) {
      const owner = taskPushOwnerAgentMeta(it);
      return {
        channel_name: String(owner.channelName || "").trim(),
        agent_name: String(owner.agentName || owner.channelName || "目标Agent").trim(),
        session_id: String(owner.sessionId || "none").trim(),
        role: String(owner.role || "none").trim(),
        alias: String(owner.alias || owner.agentName || "目标Agent").trim(),
      };
    }

    function taskPushSenderAgentRefPayload() {
      return {
        agent_name: "CCB Runtime",
        session_id: "none",
        role: "none",
        alias: "任务派发入口",
      };
    }

    function taskPushProjectExecutionContextPayload(it) {
      const sess = taskPushTargetSessionRow(it);
      const meta = buildProjectExecutionContextMeta(
        sess && (sess.project_execution_context || sess.projectExecutionContext || null)
      );
      return meta && typeof meta === "object" ? meta : {};
    }

    function taskPushSourceRefLine(it) {
      const sourceRef = taskPushSourceRefPayload(it);
      return "source_ref: project_id="
        + String(sourceRef.project_id || "").trim()
        + "; channel_name=" + String(sourceRef.channel_name || "none").trim()
        + "; session_id=" + String(sourceRef.session_id || "none").trim()
        + "; run_id=" + String(sourceRef.run_id || "none").trim();
    }

    function taskPushCallbackLine(it) {
      const cb = taskPushCallbackPayload(it);
      return "callback_to: session_id=" + String(cb.session_id || "none").trim();
    }

    function taskPushTemplateHeaderLines(it, opts = {}) {
      const target = taskPushTargetForTask(it);
      const owner = taskPushOwnerAgentMeta(it);
      const sourceChannel = taskPushSourceChannelName(it) || owner.channelName || "未识别通道";
      const targetChannel = owner.channelName || target.channelName || sourceChannel || "未识别通道";
      const projectId = String(target.projectId || (it && it.project_id) || STATE.project || "").trim() || "overview";
      const interactionMode = String((opts && opts.interactionMode) || "task_with_receipt").trim();
      const displayKind = String((opts && opts.displayKind) || "collab_update").trim();
      return [
        "[当前项目: " + projectId + "]",
        "[来源通道: " + sourceChannel + "]",
        "[目标通道: " + targetChannel + "]",
        "[目标Agent: " + (owner.agentName || targetChannel || "目标Agent") + "; session_id=" + (owner.sessionId || "none") + "; role=" + taskPushSessionRoleLabel(owner.role) + "; alias=" + (owner.alias || owner.agentName || "目标Agent") + "]",
        "[当前发信Agent: CCB Runtime; session_id=none; role=none; alias=任务派发入口]",
        taskPushCurrentSessionLine(it),
        taskPushSourceRefLine(it),
        taskPushCallbackLine(it),
        taskPushProjectExecutionContextLine(it),
        "context_binding_state: " + taskPushCurrentBindingStateLabel(it),
        "联系类型: announce_to_channel",
        "交互模式: " + interactionMode,
        "展示分类: " + displayKind,
      ];
    }

    function taskPushCollabTopic(it) {
      const code = String((it && it.code) || "").trim();
      const title = shortTitle(it && it.title) || "当前任务";
      return code ? (code + "-" + title) : title;
    }

    function taskPushTaskProgressLines(it) {
      const rows = [];
      const title = shortTitle(it && it.title) || "当前任务";
      const path = String((it && it.path) || "").trim();
      rows.push("1. 任务标题：" + title);
      if (path) rows.push("2. 任务路径：" + path);
      return rows;
    }

    function taskPushComposeCollabTemplate(it, opts = {}) {
      const topic = String((opts && opts.topic) || taskPushCollabTopic(it)).trim() || "当前任务";
      const stage = String((opts && opts.stage) || "推进").trim() || "推进";
      const goal = String((opts && opts.goal) || "").trim();
      const progressTitle = String((opts && opts.progressTitle) || "当前进展").trim() || "当前进展";
      const progressLines = Array.isArray(opts && opts.progressLines) ? opts.progressLines : [];
      const actionTitle = String((opts && opts.actionTitle) || "需要对方").trim() || "需要对方";
      const actionLines = Array.isArray(opts && opts.actionLines) ? opts.actionLines : [];
      const expectedTitle = String((opts && opts.expectedTitle) || "预期结果").trim() || "预期结果";
      const expected = String((opts && opts.expected) || "").trim();
      const extraTail = Array.isArray(opts && opts.extraTail) ? opts.extraTail : [];
      const lines = taskPushTemplateHeaderLines(it, opts);
      lines.push("回执任务: " + topic);
      lines.push("执行阶段: " + stage);
      lines.push("本次目标: " + goal);
      lines.push(progressTitle + ": " + (progressLines.length ? "" : "无"));
      for (const line of progressLines) lines.push(line);
      lines.push(actionTitle + ": " + (actionLines.length ? "" : "无"));
      for (const line of actionLines) lines.push(line);
      lines.push(expectedTitle + ": " + expected);
      for (const tail of extraTail) {
        if (String(tail || "").trim()) lines.push(String(tail).trim());
      }
      lines.push("非必要问题: 无");
      return lines.join("\n");
    }

    function taskPushDefaultMessage(it) {
      const code = String((it && it.code) || "").trim();
      const goal = code
        ? ("请继续推进任务 " + code + "，并按最新状态直接执行下一步。")
        : "请继续推进当前任务，并按最新状态直接执行下一步。";
      return taskPushComposeCollabTemplate(it, {
        topic: taskPushCollabTopic(it),
        stage: "推进",
        goal,
        progressLines: taskPushTaskProgressLines(it),
        actionLines: [
          "1. 先说明当前进度。",
          "2. 直接处理下一步，不要停在计划阶段。",
          "3. 如有阻塞，仅补充唯一阻塞与下一步动作。",
        ],
        expected: "返回可验收的推进结果，并继续完成本轮动作。",
      });
    }

    function taskPushInquiryMessage(it) {
      const code = String((it && it.code) || "").trim();
      const title = shortTitle(it && it.title) || "当前任务";
      const goal = code
        ? ("请确认任务 " + code + " 当前是否已经完成，并按结果执行收口。")
        : ("请确认任务“" + title + "”当前是否已经完成，并按结果执行收口。");
      return taskPushComposeCollabTemplate(it, {
        topic: taskPushCollabTopic(it),
        stage: "推进",
        goal,
        progressLines: taskPushTaskProgressLines(it),
        actionLines: [
          "1. 若已完成：简要说明完成结果与关键产出。",
          "2. 若已完成：将任务消费掉，更新到“已完成”并执行归档/收口。",
          "3. 若未完成：说明当前进度、剩余内容、唯一阻塞与下一步动作。",
        ],
        expected: "返回明确完成判断，并给出对应的收口或续办结论。",
      });
    }

    function taskPushSourceChannelName(it) {
      const fromState = String(STATE.channel || "").trim();
      const fromItem = String((it && it.channel) || "").trim();
      return fromState || fromItem || "";
    }

    function ensureSourceChannelMarker(text, sourceChannel) {
      const body = String(text || "").trim();
      const source = String(sourceChannel || "").trim();
      if (!body) return body;
      if (extractSourceChannelName(body)) return body;
      if (!source) return body;
      return "[来源通道: " + source + "]\n" + body;
    }

    function taskPushSetButtonLabel(btn, iconKind, text) {
      if (!btn) return;
      btn.textContent = "";
      btn.classList.add("task-push-btn");
      const ico = el("span", { class: "task-push-btn-icon " + String(iconKind || "") });
      if (String(iconKind || "").indexOf("is-send-time") >= 0) {
        ico.appendChild(el("span", { class: "tpb-clock" }));
      }
      ico.setAttribute("aria-hidden", "true");
      const label = el("span", { class: "task-push-btn-label", text: String(text || "") });
      btn.appendChild(ico);
      btn.appendChild(label);
    }

    function getTaskPushDraft(it) {
      const key = taskPushTaskKey(it);
      const cached = String(TASK_PUSH_UI.draftByTask[key] || "");
      return cached || taskPushDefaultMessage(it);
    }

    function setTaskPushDraft(it, text) {
      const key = taskPushTaskKey(it);
      TASK_PUSH_UI.draftByTask[key] = String(text || "");
    }

    function setTaskPushNote(it, text) {
      const key = taskPushTaskKey(it);
      TASK_PUSH_UI.noteByTask[key] = String(text || "");
    }

    function taskPushTargetForTask(it) {
      const projectId = String((it && it.project_id) || STATE.project || "").trim();
      const channelName = String((it && it.channel) || STATE.channel || "").trim();
      if (!projectId || projectId === "overview") {
        return { ok: false, reason: "需在具体项目下使用", projectId, channelName, sessionId: "", cliType: "codex" };
      }
      if (!channelName) {
        return { ok: false, reason: "任务未识别到通道", projectId, channelName, sessionId: "", cliType: "codex" };
      }
      const sess = sessionForChannel(projectId, channelName);
      const sessionId = String((sess && sess.session_id) || "").trim();
      const cliType = String((sess && (sess.cli_type || sess.cliType)) || "codex").trim() || "codex";
      if (!sessionId) {
        return { ok: false, reason: "该通道未绑定 session_id（请先接入/绑定主会话）", projectId, channelName, sessionId: "", cliType };
      }
      return { ok: true, reason: "", projectId, channelName, sessionId, cliType };
    }

    function taskPushSortKey(item) {
      const st = (item && item.status) || {};
      return Math.max(
        toTimeNum(st.updated_at),
        toTimeNum(st.created_at),
        0
      );
    }

    function taskPushItemsForProject(projectId) {
      const pid = String(projectId || "").trim();
      const cache = pid ? TASK_PUSH_UI.cacheByProject[pid] : null;
      return (cache && Array.isArray(cache.items)) ? cache.items : [];
    }

    function taskPushFindLatestForTask(it) {
      const key = taskPushTaskKey(it);
      const mapped = TASK_PUSH_UI.latestByTask[key];
      const target = taskPushTargetForTask(it);
      const items = taskPushItemsForProject(target.projectId).slice().sort((a, b) => taskPushSortKey(b) - taskPushSortKey(a));
      if (mapped && mapped.status && mapped.status.job_id) {
        const hit = items.find((x) => String(x.status && x.status.job_id) === String(mapped.status.job_id));
        if (hit) return hit;
      }
      if (!target.ok) return mapped || null;
      const sameTarget = items.filter((x) => {
        const st = x && x.status ? x.status : {};
        return String(st.project_id || "") === String(target.projectId)
          && String(st.target && st.target.channel_name || "") === String(target.channelName)
          && String(st.target && st.target.session_id || "") === String(target.sessionId);
      });
      const preferred = sameTarget.find((x) => {
        const s = String(x.status && x.status.status || "");
        return s === "scheduled" || s === "retry_waiting";
      }) || sameTarget[0];
      return preferred || mapped || null;
    }

    function taskPushRecentForTask(it, limit = 3) {
      const target = taskPushTargetForTask(it);
      if (!target.ok) return [];
      return taskPushItemsForProject(target.projectId)
        .filter((x) => {
          const st = x && x.status ? x.status : {};
          return String(st.target && st.target.channel_name || "") === String(target.channelName)
            && String(st.target && st.target.session_id || "") === String(target.sessionId);
        })
        .sort((a, b) => taskPushSortKey(b) - taskPushSortKey(a))
        .slice(0, Math.max(1, Number(limit || 3)));
    }

    async function fetchTaskPushProjectList(projectId, opts = {}) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return [];
      const force = !!opts.force;
      const maxAgeMs = Number(opts.maxAgeMs || 0);
      const cached = TASK_PUSH_UI.cacheByProject[pid];
      if (!force && cached && maxAgeMs > 0) {
        const age = Date.now() - Number(cached.fetchedAtMs || 0);
        if (age >= 0 && age < maxAgeMs) return cached.items || [];
      }
      if (TASK_PUSH_UI.loadingByProject[pid]) return (cached && cached.items) || [];
      TASK_PUSH_UI.loadingByProject[pid] = true;
      TASK_PUSH_UI.errorByProject[pid] = "";
      const seq = Number(TASK_PUSH_UI.seqByProject[pid] || 0) + 1;
      TASK_PUSH_UI.seqByProject[pid] = seq;
      try {
        const resp = await fetch("/api/projects/" + encodeURIComponent(pid) + "/task-push?limit=50", {
          headers: authHeaders({}),
          cache: "no-store",
        });
        if (!resp.ok) {
          const detail = await parseResponseDetail(resp);
          throw new Error(detail || ("HTTP " + resp.status));
        }
        const data = await resp.json().catch(() => ({}));
        const itemsRaw = Array.isArray(data && data.items) ? data.items : [];
        const items = itemsRaw.map(normalizeTaskPushItem);
        if (Number(TASK_PUSH_UI.seqByProject[pid] || 0) === seq) {
          TASK_PUSH_UI.cacheByProject[pid] = {
            items,
            fetchedAt: new Date().toISOString(),
            fetchedAtMs: Date.now(),
          };
        }
        return items;
      } catch (e) {
        if (Number(TASK_PUSH_UI.seqByProject[pid] || 0) === seq) {
          TASK_PUSH_UI.errorByProject[pid] = e && e.message ? String(e.message) : "网络或服务异常";
        }
        return (cached && cached.items) || [];
      } finally {
        if (Number(TASK_PUSH_UI.seqByProject[pid] || 0) === seq) {
          TASK_PUSH_UI.loadingByProject[pid] = false;
        }
      }
    }

    async function fetchTaskPushJob(projectId, jobId) {
      const pid = String(projectId || "").trim();
      const jid = String(jobId || "").trim();
      if (!pid || !jid) return null;
      const resp = await fetch(
        "/api/projects/" + encodeURIComponent(pid) + "/task-push?job_id=" + encodeURIComponent(jid),
        { headers: authHeaders({}), cache: "no-store" }
      );
      if (!resp.ok) {
        const detail = await parseResponseDetail(resp);
        throw new Error(detail || ("HTTP " + resp.status));
      }
      const data = await resp.json().catch(() => ({}));
      return data && data.item ? normalizeTaskPushItem(data.item) : null;
    }

    function maybeRerenderTaskDetail(it) {
      const modalItem = taskPushModalItem();
      if (modalItem && it && String(modalItem.path || "") === String(it.path || "")) {
        renderTaskPushModal();
      }
      const cur = selectedItem();
      if (!cur || !it) return;
      if (String(cur.path || "") !== String(it.path || "")) return;
      if (STATE.panelMode === "conv" || STATE.selectedSessionId) return;
      renderDetail(cur);
    }

    async function ensureTaskPushStateForTask(it, opts = {}) {
      const target = taskPushTargetForTask(it);
      if (!target.projectId || target.projectId === "overview") return;
      const forceSingle = !!opts.forceSingle;
      if (forceSingle) {
        const key = taskPushTaskKey(it);
        const latest = TASK_PUSH_UI.latestByTask[key];
        if (latest && latest.status && latest.status.job_id) {
          try {
            const fresh = await fetchTaskPushJob(target.projectId, latest.status.job_id);
            if (fresh) TASK_PUSH_UI.latestByTask[key] = fresh;
          } catch (_) {}
        }
      }
      await fetchTaskPushProjectList(target.projectId, opts);
      maybeRerenderTaskDetail(it);
    }

    function taskPushActionBusy(it) {
      return String(TASK_PUSH_UI.actionByTask[taskPushTaskKey(it)] || "");
    }

    async function callTaskPushAction(it, action, body) {
      const target = taskPushTargetForTask(it);
      if (!target.ok) throw new Error(target.reason || "协作消息派发目标不可用");
      const resp = await fetch("/api/projects/" + encodeURIComponent(target.projectId) + "/task-push/" + encodeURIComponent(action), {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(body || {}),
      });
      if (!resp.ok) {
        const detail = await parseResponseDetail(resp);
        const tok = getToken();
        if ((resp.status === 401 || resp.status === 403) && !tok) {
          throw new Error("服务启用了 Token 校验，请先设置 Token");
        }
        throw new Error(detail || ("HTTP " + resp.status));
      }
      return await resp.json().catch(() => ({}));
    }

    async function taskPushSendNow(it) {
      const key = taskPushTaskKey(it);
      if (TASK_PUSH_UI.actionByTask[key]) return;
      const target = taskPushTargetForTask(it);
      if (!target.ok) {
        setTaskPushNote(it, target.reason || "协作消息派发目标不可用");
        maybeRerenderTaskDetail(it);
        return;
      }
      const msg = ensureSourceChannelMarker(
        String(getTaskPushDraft(it) || "").trim(),
        taskPushSourceChannelName(it)
      );
      if (!msg) {
        setTaskPushNote(it, "协作消息不能为空");
        maybeRerenderTaskDetail(it);
        return;
      }
      setTaskPushDraft(it, msg);
      TASK_PUSH_UI.actionByTask[key] = "send-now";
      setTaskPushNote(it, "正在立即派发协作消息…");
      maybeRerenderTaskDetail(it);
      try {
        const sourceRef = taskPushSourceRefPayload(it);
        const callbackTo = taskPushCallbackPayload(it);
        const ownerRef = taskPushOwnerRefPayload(it);
        const senderAgentRef = taskPushSenderAgentRefPayload();
        const projectExecutionContext = taskPushProjectExecutionContextPayload(it);
        const payload = {
          channel_name: target.channelName,
          session_id: target.sessionId,
          message: msg,
          profile_label: "task-push-ui",
          message_kind: "collab_update",
          source_ref: sourceRef,
          callback_to: callbackTo,
          owner_ref: ownerRef,
          sender_agent_ref: senderAgentRef,
          project_execution_context: projectExecutionContext,
          run_extra_meta: {
            trigger_type: "task_push_manual_ui",
            task_path: String((it && it.path) || ""),
            task_title: String((it && it.title) || ""),
            message_kind: "collab_update",
            owner_channel_name: String(target.channelName || ""),
            execution_stage: "推进",
            source_ref: sourceRef,
            callback_to: callbackTo,
            owner_ref: ownerRef,
            sender_agent_ref: senderAgentRef,
            project_execution_context: projectExecutionContext,
          },
        };
        const data = await callTaskPushAction(it, "send-now", payload);
        let item = data && data.item ? normalizeTaskPushItem(data.item) : null;
        if (item) TASK_PUSH_UI.latestByTask[key] = item;
        if (taskPushIsImmediateActiveSkipPlaceholder(item)) {
          setTaskPushNote(it, "目标会话当前活跃，已自动转为定时协作派发（最多2轮）。");
          const schedulePayload = {
            channel_name: target.channelName,
            session_id: target.sessionId,
            message: msg,
            retry_interval_seconds: 60,
            max_attempts: 2,
            profile_label: "task-push-ui",
            message_kind: "collab_update",
            source_ref: sourceRef,
            callback_to: callbackTo,
            owner_ref: ownerRef,
            sender_agent_ref: senderAgentRef,
            project_execution_context: projectExecutionContext,
            run_extra_meta: {
              trigger_type: "task_push_manual_send_now_auto_schedule_fallback",
              task_path: String((it && it.path) || ""),
              task_title: String((it && it.title) || ""),
              source_mode: "immediate",
              message_kind: "collab_update",
              owner_channel_name: String(target.channelName || ""),
              execution_stage: "推进",
              source_ref: sourceRef,
              callback_to: callbackTo,
              owner_ref: ownerRef,
              sender_agent_ref: senderAgentRef,
              project_execution_context: projectExecutionContext,
            },
          };
          const fallbackData = await callTaskPushAction(it, "schedule", schedulePayload);
          const fallbackItem = fallbackData && fallbackData.item ? normalizeTaskPushItem(fallbackData.item) : null;
          if (fallbackItem) {
            item = fallbackItem;
            TASK_PUSH_UI.latestByTask[key] = fallbackItem;
          }
        } else {
          setTaskPushNote(it, "已触发立即协作派发。");
        }
        await ensureTaskPushStateForTask(it, { force: true });
        await refreshConversationPanelAfterTaskPush(it, { kickPoll: true, pollMs: 1200 });
      } catch (e) {
        setTaskPushNote(it, "立即派发失败：" + String((e && e.message) || e || "未知错误"));
        maybeRerenderTaskDetail(it);
      } finally {
        delete TASK_PUSH_UI.actionByTask[key];
        maybeRerenderTaskDetail(it);
      }
    }

    async function taskPushSchedule(it) {
      const key = taskPushTaskKey(it);
      if (TASK_PUSH_UI.actionByTask[key]) return;
      const target = taskPushTargetForTask(it);
      if (!target.ok) {
        setTaskPushNote(it, target.reason || "协作消息派发目标不可用");
        maybeRerenderTaskDetail(it);
        return;
      }
      const msg = ensureSourceChannelMarker(
        String(getTaskPushDraft(it) || "").trim(),
        taskPushSourceChannelName(it)
      );
      if (!msg) {
        setTaskPushNote(it, "协作消息不能为空");
        maybeRerenderTaskDetail(it);
        return;
      }
      setTaskPushDraft(it, msg);
      TASK_PUSH_UI.actionByTask[key] = "schedule";
      setTaskPushNote(it, "正在创建定时协作派发（最多2轮）…");
      maybeRerenderTaskDetail(it);
      try {
        const sourceRef = taskPushSourceRefPayload(it);
        const callbackTo = taskPushCallbackPayload(it);
        const ownerRef = taskPushOwnerRefPayload(it);
        const senderAgentRef = taskPushSenderAgentRefPayload();
        const projectExecutionContext = taskPushProjectExecutionContextPayload(it);
        const payload = {
          channel_name: target.channelName,
          session_id: target.sessionId,
          message: msg,
          retry_interval_seconds: 60,
          max_attempts: 2,
          profile_label: "task-push-ui",
          message_kind: "collab_update",
          source_ref: sourceRef,
          callback_to: callbackTo,
          owner_ref: ownerRef,
          sender_agent_ref: senderAgentRef,
          project_execution_context: projectExecutionContext,
          run_extra_meta: {
            trigger_type: "task_push_manual_schedule_ui",
            task_path: String((it && it.path) || ""),
            task_title: String((it && it.title) || ""),
            message_kind: "collab_update",
            owner_channel_name: String(target.channelName || ""),
            execution_stage: "推进",
            source_ref: sourceRef,
            callback_to: callbackTo,
            owner_ref: ownerRef,
            sender_agent_ref: senderAgentRef,
            project_execution_context: projectExecutionContext,
          },
        };
        const data = await callTaskPushAction(it, "schedule", payload);
        const item = data && data.item ? normalizeTaskPushItem(data.item) : null;
        if (item) TASK_PUSH_UI.latestByTask[key] = item;
        setTaskPushNote(it, "已创建定时协作派发：若目标会话活跃，将自动循环检查（最多2轮）。");
        await ensureTaskPushStateForTask(it, { force: true });
        await refreshConversationPanelAfterTaskPush(it);
      } catch (e) {
        setTaskPushNote(it, "定时派发失败：" + String((e && e.message) || e || "未知错误"));
        maybeRerenderTaskDetail(it);
      } finally {
        delete TASK_PUSH_UI.actionByTask[key];
        maybeRerenderTaskDetail(it);
      }
    }

    async function taskPushCancel(it, jobId) {
      const key = taskPushTaskKey(it);
      if (TASK_PUSH_UI.actionByTask[key]) return;
      const jid = String(jobId || "").trim();
      if (!jid) return;
      TASK_PUSH_UI.actionByTask[key] = "cancel";
      setTaskPushNote(it, "正在取消定时协作派发…");
      maybeRerenderTaskDetail(it);
      try {
        const data = await callTaskPushAction(it, "cancel", { job_id: jid, reason: "user_cancel" });
        const item = data && data.item ? normalizeTaskPushItem(data.item) : null;
        if (item) TASK_PUSH_UI.latestByTask[key] = item;
        setTaskPushNote(it, "已取消本次协作消息派发。");
        await ensureTaskPushStateForTask(it, { force: true });
        await refreshConversationPanelAfterTaskPush(it);
      } catch (e) {
        setTaskPushNote(it, "取消失败：" + String((e && e.message) || e || "未知错误"));
        maybeRerenderTaskDetail(it);
      } finally {
        delete TASK_PUSH_UI.actionByTask[key];
        maybeRerenderTaskDetail(it);
      }
    }

    async function refreshConversationPanelAfterTaskPush(it, opts = {}) {
      const target = taskPushTargetForTask(it);
      if (!target.ok) return;
      const currentProjectId = String(STATE.project || "").trim();
      const targetProjectId = String(target.projectId || "").trim();
      if (!currentProjectId || !targetProjectId || currentProjectId !== targetProjectId) return;
      try {
        await refreshConversationPanel();
        if (opts && opts.kickPoll) {
          const ms = Number(opts.pollMs);
          scheduleConversationPoll(Number.isFinite(ms) && ms > 0 ? ms : 1200);
        }
      } catch (_) {}
    }

    function renderTaskPushAttempts(listWrap, latest) {
      const attempts = Array.isArray(latest && latest.attempts) ? latest.attempts : [];
      if (!attempts.length) {
        listWrap.appendChild(el("div", { class: "task-push-empty", text: "暂无尝试记录。" }));
        return;
      }
      const ul = el("div", { class: "task-push-attempts" });
      for (const a of attempts) {
        const row = el("div", { class: "task-push-attempt" });
        const top = el("div", { class: "task-push-attempt-top" });
        top.appendChild(chip("#" + String(a.attempt || "-"), "muted"));
        if (a.trigger) top.appendChild(chip(String(a.trigger), "muted"));
        top.appendChild(chip(taskPushAttemptResultLabel(a.result), a.result === "dispatched" ? "good" : (a.result === "dispatch_error" ? "bad" : "warn")));
        if (a.active) top.appendChild(chip("会话活跃:" + (a.active_status || "-"), "warn"));
        row.appendChild(top);
        const meta = [];
        if (a.attempted_at) meta.push("执行 " + formatTsOrDash(a.attempted_at));
        if (a.due_at) meta.push("计划 " + formatTsOrDash(a.due_at));
        if (a.run_id) meta.push("run " + shortId(a.run_id));
        if (meta.length) row.appendChild(el("div", { class: "task-push-attempt-sub", text: meta.join(" · ") }));
        if (a.error) row.appendChild(el("div", { class: "task-push-attempt-err", text: a.error }));
        ul.appendChild(row);
      }
      listWrap.appendChild(ul);
    }

    function renderTaskPushCard(it, opts = {}) {
      const force = !!opts.force;
      if (!it) return null;
      if (!force && (STATE.panelMode === "conv" || STATE.selectedSessionId)) return null;
      const projectId = String((it.project_id || STATE.project) || "").trim();
      if (!projectId || projectId === "overview") return null;
      const key = taskPushTaskKey(it);
      const target = taskPushTargetForTask(it);
      const actionBusy = taskPushActionBusy(it);
      const note = String(TASK_PUSH_UI.noteByTask[key] || "").trim();
      const latest = taskPushFindLatestForTask(it);
      const projectCache = TASK_PUSH_UI.cacheByProject[projectId];
      const loading = !!TASK_PUSH_UI.loadingByProject[projectId];
      const err = String(TASK_PUSH_UI.errorByProject[projectId] || "").trim();

      const card = el("section", { class: "task-push-card" });
      const head = el("div", { class: "task-push-head" });
      const titleWrap = el("div", { class: "task-push-titlewrap" });
      titleWrap.appendChild(el("div", { class: "task-push-kicker", text: "协作消息派发" }));
      titleWrap.appendChild(el("div", { class: "task-push-title", text: "新版协作模板（立即 / 定时重试）" }));
      const sub = target.ok
        ? ("目标通道：" + target.channelName + " · 主会话：" + shortId(target.sessionId))
        : ("目标不可用：" + (target.reason || "未识别"));
      titleWrap.appendChild(el("div", { class: "task-push-sub", text: sub }));
      head.appendChild(titleWrap);
      const headOps = el("div", { class: "task-push-head-ops" });
      const refreshBtn = el("button", { class: "btn", text: loading ? "刷新中..." : "刷新状态" });
      refreshBtn.disabled = loading || !!actionBusy;
      refreshBtn.addEventListener("click", () => {
        setTaskPushNote(it, "正在刷新协作消息派发状态…");
        maybeRerenderTaskDetail(it);
        ensureTaskPushStateForTask(it, { force: true });
      });
      headOps.appendChild(refreshBtn);
      head.appendChild(headOps);
      card.appendChild(head);

      if (err) {
        card.appendChild(el("div", { class: "task-push-error", text: "状态查询失败：" + err }));
      }
      if (note) {
        card.appendChild(el("div", { class: "task-push-note" + (note.includes("失败") ? " error" : ""), text: note }));
      }

      const editor = el("div", { class: "task-push-editor" });
      const textarea = el("textarea", {
        class: "task-push-textarea",
        placeholder: "输入协作消息模板（将派发到该任务所属通道的主会话）",
      });
      textarea.value = getTaskPushDraft(it);
      textarea.addEventListener("input", () => setTaskPushDraft(it, textarea.value));
      editor.appendChild(textarea);

      const editorOps = el("div", { class: "task-push-editor-ops" });
      const inquiryBtn = el("button", { class: "btn" });
      taskPushSetButtonLabel(inquiryBtn, "is-text", "完成确认模板");
      inquiryBtn.disabled = !!actionBusy;
      inquiryBtn.title = "填充“确认是否完成 + 完成则收口”的新版协作模板";
      inquiryBtn.addEventListener("click", () => {
        const next = taskPushInquiryMessage(it);
        textarea.value = next;
        setTaskPushDraft(it, next);
      });
      editorOps.appendChild(inquiryBtn);

      const resetBtn = el("button", { class: "btn" });
      taskPushSetButtonLabel(resetBtn, "is-text", "协作派发模板");
      resetBtn.disabled = !!actionBusy;
      resetBtn.addEventListener("click", () => {
        const next = taskPushDefaultMessage(it);
        textarea.value = next;
        setTaskPushDraft(it, next);
      });
      editorOps.appendChild(resetBtn);

      const sendNowBtn = el("button", { class: "btn primary" });
      taskPushSetButtonLabel(sendNowBtn, "is-send", actionBusy === "send-now" ? "派发中..." : "立即派发");
      sendNowBtn.disabled = !target.ok || !!actionBusy;
      sendNowBtn.addEventListener("click", () => {
        setTaskPushDraft(it, textarea.value);
        taskPushSendNow(it);
      });
      editorOps.appendChild(sendNowBtn);

      const scheduleBtn = el("button", { class: "btn" });
      taskPushSetButtonLabel(scheduleBtn, "is-send-time", actionBusy === "schedule" ? "创建中..." : "定时派发（2轮）");
      scheduleBtn.disabled = !target.ok || !!actionBusy;
      scheduleBtn.title = "若目标会话活跃，将每60秒再尝试一次，最多2轮";
      scheduleBtn.addEventListener("click", () => {
        setTaskPushDraft(it, textarea.value);
        taskPushSchedule(it);
      });
      editorOps.appendChild(scheduleBtn);
      editor.appendChild(editorOps);
      card.appendChild(editor);

      const latestWrap = el("div", { class: "task-push-latest" });
      latestWrap.appendChild(el("div", { class: "task-push-section-title", text: "当前协作消息派发状态" }));
      if (!latest) {
        latestWrap.appendChild(el("div", { class: "task-push-empty", text: loading ? "状态加载中..." : "暂无协作消息派发记录（可直接点击“立即派发”或“定时派发”）。" }));
      } else {
        const st = latest.status || {};
        const hasPlannedRetry = taskPushHasPlannedRetry(st);
        const summaryTop = el("div", { class: "task-push-summary-top" });
        summaryTop.appendChild(chip(taskPushModeLabel(st.mode), "muted"));
        summaryTop.appendChild(chip(taskPushDisplayStatusLabel(latest), taskPushDisplayStatusTone(latest)));
        if (hasPlannedRetry && st.retryable) summaryTop.appendChild(chip("可取消", "warn"));
        if (st.attempt_count > 0) summaryTop.appendChild(chip("尝试 " + st.attempt_count + "/" + Math.max(st.max_attempts || st.attempt_count, st.attempt_count), "muted"));
        latestWrap.appendChild(summaryTop);

        const grid = el("div", { class: "task-push-meta-grid" });
        const addMeta = (k, v, cls = "") => {
          if (!String(v || "").trim()) return;
          const row = el("div", { class: "task-push-meta-row" + (cls ? (" " + cls) : "") });
          row.appendChild(el("div", { class: "task-push-meta-k", text: k }));
          row.appendChild(el("div", { class: "task-push-meta-v", text: v }));
          grid.appendChild(row);
        };
        addMeta("job", st.job_id || "-", "mono");
        addMeta("更新时间", formatTsOrDash(st.updated_at || st.created_at));
        addMeta("最近结果", st.last_result ? taskPushAttemptResultLabel(st.last_result) : "-");
        if (hasPlannedRetry) addMeta("下次执行", formatTsOrDash(st.next_due_at));
        addMeta("最近run", st.last_run_id || "-", "mono");
        if (st.last_error) addMeta("错误", st.last_error, "error");
        latestWrap.appendChild(grid);

        const canCancel = !!st.retryable && !!st.job_id && hasPlannedRetry;
        if (canCancel) {
          const cancelRow = el("div", { class: "task-push-cancel-row" });
          const cancelBtn = el("button", { class: "btn danger", text: actionBusy === "cancel" ? "取消中..." : "取消本次定时派发" });
          cancelBtn.disabled = !!actionBusy;
          cancelBtn.addEventListener("click", () => taskPushCancel(it, st.job_id));
          cancelRow.appendChild(cancelBtn);
          latestWrap.appendChild(cancelRow);
        }

        renderTaskPushAttempts(latestWrap, latest);
      }
      card.appendChild(latestWrap);
      const cacheTip = projectCache && projectCache.fetchedAt ? ("项目级缓存刷新于 " + compactDateTime(projectCache.fetchedAt)) : "";
      if (cacheTip) {
        card.appendChild(el("div", { class: "task-push-foot" , text: cacheTip }));
      }

      return card;
    }
