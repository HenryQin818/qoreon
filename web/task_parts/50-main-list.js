    // task.js 第五刀：主列表 shell / list data adapter
    function buildItemSortControl() {
      const wrap = el("span", { class: "conv-sort-inline" });
      wrap.appendChild(el("span", { class: "conv-sort-label", text: "排序" }));
      const select = el("select", { class: "conv-sort-select", "aria-label": "列表排序" });
      const current = normalizeItemSort(STATE && STATE.itemSort);
      for (const opt of ITEM_SORT_OPTIONS) {
        const node = el("option", { value: opt.value, text: opt.label });
        if (opt.value === current) node.selected = true;
        select.appendChild(node);
      }
      select.addEventListener("change", () => setItemSort(select.value));
      wrap.appendChild(select);
      return wrap;
    }

    function typeOptions() {
      const preferred = ["任务", "需求", "问题", "反馈", "答复", "讨论"];
      const types = Array.from(new Set(allItems().map((x) => String(x.type || "")).filter(Boolean)));
      const extra = types.filter((t) => !preferred.includes(t)).sort((a, b) => a.localeCompare(b, "zh-Hans-CN"));
      return ["全部", ...preferred.filter((t) => types.includes(t)), ...extra];
    }

    function statusOptions() {
      return ["待办", "进行中", "已完成", "全部"];
    }

    function scopeItems() {
      if (STATE.view === "comms") {
        if (STATE.project === "overview") return [];
        if (!STATE.channel) return [];
        const base = itemsForProject(STATE.project).filter((x) => String(x.channel || "") === String(STATE.channel));
        const comms = base.filter(isDiscussionSpaceItem).filter(matchesQuery);
        comms.sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")));
        return comms;
      }
      if (STATE.project === "overview") return filteredItemsForProject("overview");
      if (!STATE.channel) return [];
      return filteredItemsForProject(STATE.project).filter((x) => String(x.channel || "") === String(STATE.channel));
    }

    function sortItemsInList(items) {
      return sortListItems(items);
    }

    function buildMainList() {
      const proj = projectById(STATE.project);
      const mainMeta = document.getElementById("mainMeta");
      const bar = document.getElementById("filterBar");
      const list = document.getElementById("fileList");
      const materialsHeader = document.getElementById("taskMaterialsHeader");

      bar.innerHTML = "";
      list.innerHTML = "";
      if (materialsHeader) {
        materialsHeader.style.display = (STATE.panelMode === "channel") ? "" : "none";
      }
      renderChannelInfoCard();

      if (STATE.panelMode === "conv") {
        if (mainMeta) {
          mainMeta.textContent = "view=项目对话 · scope=" + ((proj ? proj.name : STATE.project) || "-") + " · generated_at=" + DATA.generated_at;
        }
        buildConversationMainList(list);
        return;
      }

      if (STATE.panelMode === "org") {
        if (mainMeta) {
          const orgSnapshot = orgBoardSnapshot(STATE.project);
          const orgRuntime = orgBoardRuntime(STATE.project);
          const orgNodeCount = Array.isArray(orgSnapshot.nodes) ? orgSnapshot.nodes.length : 0;
          const orgRelCount = Array.isArray(orgRuntime.runtime_relations) ? orgRuntime.runtime_relations.length : 0;
          mainMeta.textContent = "view=组织视图 · 节点=" + orgNodeCount + " · 运行态关系=" + orgRelCount + " · generated_at=" + DATA.generated_at;
        }
        buildOrgModeList(list, mainMeta, { view: "org" });
        return;
      }

      if (STATE.panelMode === "arch") {
        if (mainMeta) {
          const orgSnapshot = orgBoardSnapshot(STATE.project);
          const orgRuntime = orgBoardRuntime(STATE.project);
          const orgNodeCount = Array.isArray(orgSnapshot.nodes) ? orgSnapshot.nodes.length : 0;
          const orgRelCount = Array.isArray(orgRuntime.runtime_relations) ? orgRuntime.runtime_relations.length : 0;
          mainMeta.textContent = "view=架构2D画板 · 节点=" + orgNodeCount + " · 运行态关系=" + orgRelCount + " · generated_at=" + DATA.generated_at;
        }
        buildOrgModeList(list, mainMeta, { view: "arch" });
        return;
      }

      if (STATE.panelMode === "task") {
        buildTaskModeList(list, bar, mainMeta);
        return;
      }

      let items = scopeItems();
      items = sortItemsInList(items);
      const itemsLoading = isProjectItemsLoading(STATE.project);
      const itemsLoadError = itemLoadErrorForProject(STATE.project);

      const scopeLabel = (STATE.project === "overview")
        ? "总览（跨项目）"
        : ("项目:" + (proj ? proj.name : STATE.project) + " · 通道:" + (STATE.channel || "-"));
      const viewLabel = (STATE.view === "comms") ? "沟通通道" : "工作任务";
      if (mainMeta) {
        const loadingSuffix = itemsLoading ? " · loading=1" : "";
        mainMeta.textContent = "view=" + viewLabel + " · scope=" + scopeLabel + " · generated_at=" + DATA.generated_at + " · items=" + items.length + loadingSuffix;
      }

      if (STATE.view === "work") {
        const typeRow = el("div", { class: "filterrow" });
        for (const t of typeOptions()) {
          typeRow.appendChild(chipButton(t === "全部" ? "全部" : t, STATE.type === t, () => {
            STATE.type = t;
            STATE.selectedPath = "";
            setHash();
            render();
          }));
        }

        const statusRow = el("div", { class: "filterrow" });
        for (const s of statusOptions()) {
          statusRow.appendChild(chipButton(s, STATE.status === s, () => {
            STATE.status = s;
            STATE.selectedPath = "";
            setHash();
            render();
          }));
        }

        bar.appendChild(typeRow);
        bar.appendChild(statusRow);
        const sortRow = el("div", { class: "filterrow" });
        sortRow.appendChild(buildItemSortControl());
        bar.appendChild(sortRow);
      } else {
        const info = el("div", { class: "filterrow" });
        info.appendChild(chip("仅加载：讨论空间", "muted"));
        info.appendChild(buildItemSortControl());
        bar.appendChild(info);
      }

      if (!items.length && itemsLoading) {
        list.appendChild(el("div", { class: "hint", text: "正在加载当前项目数据..." }));
        return;
      }

      if (!items.length && itemsLoadError) {
        list.appendChild(el("div", { class: "hint", text: "当前项目数据加载失败，请稍后重试。" }));
        return;
      }

      if (!items.length) {
        list.appendChild(el("div", { class: "hint", text: "当前筛选条件下没有匹配的事项。" }));
        return;
      }

      for (const it of items.slice(0, 260)) {
        const path = String(it.path || "");
        const row = el("div", {
          class: "frow" + (path && path === String(STATE.selectedPath || "") ? " active" : ""),
          "data-path": path
        });
        bindTaskScheduleDragSource(row, it);

        const titleRow = el("div", { class: "mainlist-title-row" });
        titleRow.appendChild(buildItemTitleNode(it, "t"));
        const titleOps = el("div", { class: "frow-title-ops" });

        if (STATE.view === "work" && path && isTaskItem(it)) {
          const currentStatus = it.status || parseStatusFromTitle(it.title) || "待处理";
          const statusSelector = createStatusSelector(currentStatus, path, (result) => {
            STATE.selectedPath = String((result && result.new_path) || path || "");
            render();
          });
          titleOps.appendChild(statusSelector);
        }

        if (STATE.view === "work" && isTaskItem(it)) {
          const scheduleBtn = createTaskScheduleToggleBtn(it, true);
          if (scheduleBtn) titleOps.appendChild(scheduleBtn);
          const pushBtn = createTaskPushEntryBtn(it, true);
          if (pushBtn) titleOps.appendChild(pushBtn);
        }
        if (titleOps.childNodes.length) {
          titleRow.appendChild(titleOps);
        }

        row.appendChild(titleRow);

        const meta = el("div", { class: "m" });
        const bucket = bucketKeyForStatus(it.status);
        if (STATE.view === "work") meta.appendChild(chip(bucket, toneForBucket(bucket)));
        if (STATE.project === "overview") meta.appendChild(chip(it.project_name || it.project_id, "muted"));
        if (it.channel) meta.appendChild(chip(it.channel, "muted"));
        if (it.code) meta.appendChild(chip(it.code, "muted"));
        const hasScheduleBtn = !!titleOps.querySelector(".taskschedule-entry-btn");
        if (isTaskScheduledByItem(it) && !hasScheduleBtn) meta.appendChild(chip("已排期", "good"));
        if (it.owner) meta.appendChild(chip("负责人:" + it.owner, "muted"));
        if (it.updated_at) meta.appendChild(chip("更新:" + it.updated_at, "muted"));
        row.appendChild(meta);
        row.appendChild(el("div", { class: "p", text: path }));
        row.addEventListener("click", () => setSelectedPath(it.path));
        list.appendChild(row);
      }
    }
