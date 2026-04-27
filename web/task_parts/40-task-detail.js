    // task.js 第四刀：任务详情 shell / detail adapter
    function renderDetail(it) {
      const titleEl = document.getElementById("detailTitle");
      const subEl = document.getElementById("detailSub");
      const metaEl = document.getElementById("detailMeta");
      const exEl = document.getElementById("detailExcerpt");
      const moreEl = document.getElementById("detailMore");
      const pathBar = document.getElementById("detailPathBar");
      const pathText = document.getElementById("detailPathText");
      const revealBtn = document.getElementById("detailRevealBtn");
      const detailMemoBtn = document.getElementById("detailMemoBtn");
      const detailTaskPushBtn = document.getElementById("detailTaskPushBtn");
      const convWrap = document.getElementById("convWrap");
      const ccbBox = document.getElementById("ccbBox");

      if (STATE.selectedSessionId && STATE.panelMode !== "conv" && STATE.panelMode !== "channel") {
        if (metaEl) metaEl.style.display = "none";
        if (exEl) exEl.style.display = "none";
        if (moreEl) moreEl.style.display = "none";
        if (detailTaskPushBtn) detailTaskPushBtn.style.display = "none";
        if (detailMemoBtn) detailMemoBtn.style.display = "";
        if (ccbBox) ccbBox.style.display = "none";
        if (convWrap) convWrap.classList.add("show");
        renderConversationDetail();
        return;
      }

      if (STATE.panelMode === "conv") {
        if (convWrap) convWrap.classList.add("show");
        if (metaEl) metaEl.style.display = "none";
        if (exEl) exEl.style.display = "none";
        if (moreEl) moreEl.style.display = "none";
        if (detailTaskPushBtn) detailTaskPushBtn.style.display = "none";
        if (detailMemoBtn) detailMemoBtn.style.display = "";
        if (ccbBox) ccbBox.style.display = "none";
        renderConversationDetail();
        return;
      }

      if (convWrap) convWrap.classList.remove("show");
      if (metaEl) metaEl.style.display = "";
      if (exEl) exEl.style.display = "";
      if (moreEl) moreEl.style.display = "";
      if (detailMemoBtn) {
        detailMemoBtn.style.display = "none";
        detailMemoBtn.onclick = null;
      }
      if (ccbBox) ccbBox.style.display = "none";
      hideConversationMemoEntry();
      if (subEl) subEl.textContent = "";

      metaEl.innerHTML = "";
      moreEl.innerHTML = "";

      const scopeProjectId = it ? String(it.project_id || "") : String(STATE.project || "");
      const scopeChannel = it ? String(it.channel || "") : String(STATE.channel || "");
      const scopeProject = (scopeProjectId && scopeProjectId !== "overview") ? projectById(scopeProjectId) : null;
      const sess = (scopeProjectId && scopeChannel && scopeProjectId !== "overview") ? sessionForChannel(scopeProjectId, scopeChannel) : null;
      const sid = sess && sess.session_id ? String(sess.session_id).trim() : "";

      if (pathBar) pathBar.style.display = "none";
      if (pathText) pathText.textContent = "";
      if (revealBtn) {
        revealBtn.disabled = true;
        revealBtn.onclick = () => {};
      }

      if (!it) {
        titleEl.textContent = scopeChannel
          ? ((STATE.panelMode === "channel" ? "未选择文件" : "未选择事项") + "（" + scopeChannel + "）")
          : (STATE.panelMode === "channel" ? "未选择文件" : "未选择事项");
        if (subEl) subEl.textContent = "";
        if (detailTaskPushBtn) {
          detailTaskPushBtn.style.display = "none";
          detailTaskPushBtn.onclick = null;
        }
        setMarkdown(exEl, "", STATE.panelMode === "channel" ? "(点击左侧文件或知识条目，在此查看详情)" : "(点击列表任意行，在此查看详情)");

        if (scopeProject && Array.isArray(scopeProject.links) && scopeProject.links.length) {
          metaEl.appendChild(chip(scopeProject.name || scopeProject.id, "muted"));
          for (const lk of scopeProject.links.slice(0, 6)) {
            metaEl.appendChild(chipLink(lk.label || "链接", lk.url || ""));
          }
        }
        return;
      }

      titleEl.innerHTML = "";
      titleEl.appendChild(buildItemTitleNode(it, "detail-title-text", { detail: true }));
      if (subEl) subEl.textContent = "";
      const bucket = bucketKeyForStatus(it.status);

      if (detailTaskPushBtn) {
        if (isTaskItem(it) && STATE.panelMode !== "conv") {
          detailTaskPushBtn.style.display = "";
          detailTaskPushBtn.onclick = (e) => {
            e.preventDefault();
            openTaskPushModalByItem(it);
          };
        } else {
          detailTaskPushBtn.style.display = "none";
          detailTaskPushBtn.onclick = null;
        }
      }
      const itemPath = String(it.path || "");
      if (STATE.panelMode !== "channel" && STATE.view === "work" && itemPath && isTaskItem(it)) {
        const currentStatus = it.status || parseStatusFromTitle(it.title) || "待处理";
        const statusSelector = createStatusSelector(currentStatus, itemPath, (result) => {
          setSelectedTaskRef(result.new_path || "", taskStableIdOfItem(it));
          render();
        });
        metaEl.appendChild(statusSelector);
      }

      if (STATE.project === "overview") metaEl.appendChild(chip(it.project_name || it.project_id, "muted"));
      metaEl.appendChild(chip(it.channel || "未归类", "muted"));
      if (STATE.panelMode === "channel") {
        const groupLabel = inferKnowledgeGroupLabel(it);
        metaEl.appendChild(chip(groupLabel, "muted"));
        const typeLabel = String((it && it.type) || "").trim();
        if (typeLabel && typeLabel !== groupLabel) metaEl.appendChild(chip(typeLabel, "muted"));
      } else {
        const primaryStatus = taskPrimaryStatus(it);
        const flags = taskStatusFlags(it);
        metaEl.appendChild(chip(primaryStatus || bucket, taskPrimaryTone(primaryStatus || bucket)));
        if (flags.supervised) metaEl.appendChild(chip("关注", "bad"));
        if (flags.blocked) metaEl.appendChild(chip("阻塞", "bad"));
        if (isTaskItem(it) && primaryStatus === "进行中") {
          const autoState = taskAutoKickoffStateForTask(it);
          metaEl.appendChild(chip("首发:" + autoState.label, autoState.tone));
        }
        if (it.code) metaEl.appendChild(chip(it.code, "muted"));
        if (isTaskScheduledByItem(it)) metaEl.appendChild(chip("已排期", "good"));
        if (it.owner) metaEl.appendChild(chip("负责人:" + it.owner, "muted"));
        if (it.due) metaEl.appendChild(chip("截止:" + it.due, "warn"));
      }
      if (it.updated_at) metaEl.appendChild(chip("更新:" + it.updated_at, "muted"));
      if (scopeProject && Array.isArray(scopeProject.links) && scopeProject.links.length) {
        for (const lk of scopeProject.links.slice(0, 6)) {
          metaEl.appendChild(chipLink(lk.label || "链接", lk.url || ""));
        }
      }

      if (isTaskItem(it) && typeof renderUnifiedTaskDetailInline === "function") {
        renderUnifiedTaskDetailInline(exEl, it, {
          source: "task-detail-panel",
          projectId: scopeProjectId,
          channelName: it.channel || scopeChannel,
        });
      } else {
        setMarkdown(exEl, it.excerpt || "", "(empty)");
      }
      const kickoffCard = renderTaskAutoKickoffCard(it);
      if (kickoffCard) moreEl.appendChild(kickoffCard);
      const assistCard = renderAssistRequestCard(it);
      if (assistCard) moreEl.appendChild(assistCard);
      if (isTaskItem(it)) {
        const assistKey = assistTaskKey(it);
        const assistCache = ASSIST_UI.cacheByTask[assistKey];
        const assistStale = !assistCache || ((Date.now() - Number(assistCache.fetchedAtMs || 0)) > 5000);
        if (assistStale && !ASSIST_UI.loadingByTask[assistKey]) {
          fetchAssistRequestsForTask(it, { maxAgeMs: 5000 }).catch(() => {});
        }

        const taskProjectId = String((it && it.project_id) || "").trim();
        const taskPushCache = taskProjectId ? TASK_PUSH_UI.cacheByProject[taskProjectId] : null;
        const taskPushStale = !taskPushCache || ((Date.now() - Number(taskPushCache.fetchedAtMs || 0)) > 5000);
        if (taskPushStale && !TASK_PUSH_UI.loadingByProject[taskProjectId]) {
          ensureTaskPushStateForTask(it, { maxAgeMs: 5000 }).catch(() => {});
        }
      }

      if (itemPath && pathBar && pathText && revealBtn) {
        pathBar.style.display = "";
        pathText.textContent = itemPath;
        pathText.title = "点击复制路径";
        pathText.onclick = () => copyText(itemPath);

        revealBtn.disabled = false;
        revealBtn.onclick = async (e) => {
          e.preventDefault();
          e.stopPropagation();
          revealBtn.disabled = true;
          try {
            const ok = await apiHealth();
            if (!ok) {
              alert("本机服务不可用，无法打开文件夹。");
              return;
            }
            const resp = await fetch("/api/fs/reveal", {
              method: "POST",
              headers: authHeaders({ "Content-Type": "application/json" }),
              body: JSON.stringify({ path: itemPath }),
            });
            if (!resp.ok) {
              let detail = "请求失败（HTTP " + resp.status + "）";
              try {
                const j = await resp.json();
                const msg = String((j && (j.error || j.message)) || "").trim();
                if (msg) detail = msg;
              } catch (_) {}
              alert("打开文件夹失败：" + detail);
            }
          } catch (err) {
            alert("打开文件夹失败：" + String((err && err.message) || err || "未知错误"));
          } finally {
            revealBtn.disabled = false;
          }
        };
      }

      if (!sid && STATE.panelMode !== "channel") {
        if (scopeProjectId !== "overview" && scopeChannel) {
          moreEl.appendChild(el("div", {
            class: "hint",
            text: "该通道未绑定 session_id：可在右侧「通道对话（CCB）」处点击【绑定对话】快速绑定（仅保存在本机浏览器），建议后续同步到 config.toml 以便团队一致。"
          }));
        }
      }
    }
