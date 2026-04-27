    // Shared task list cards for task homepage and conversation side task panel.
    function unifiedTaskListText(value) {
      return String(value == null ? "" : value).trim();
    }

    function unifiedTaskListTime(value) {
      const text = unifiedTaskListText(value);
      if (!text) return "";
      if (typeof compactDateTime === "function") return compactDateTime(text) || text;
      if (typeof shortDateTime === "function") return shortDateTime(text) || text;
      return text;
    }

    function unifiedTaskListTypeLabel(typeKey) {
      return String(typeKey || "") === "child" ? "子任务" : "主任务";
    }

    function unifiedTaskListTone(statusText) {
      if (typeof unifiedTaskDetailTone === "function") return unifiedTaskDetailTone(statusText);
      if (typeof taskPrimaryTone === "function") return taskPrimaryTone(statusText);
      return "muted";
    }

    function unifiedTaskListRoleMemberText(member) {
      if (typeof taskRoleMemberDisplayMeta === "function") {
        const meta = taskRoleMemberDisplayMeta(member);
        return unifiedTaskListText(meta && meta.text);
      }
      return unifiedTaskListText(member && (member.display_name || member.name || member.alias || member.agent_name));
    }

    function unifiedTaskListRoleMemberKey(member, text) {
      const item = (member && typeof member === "object") ? member : {};
      return [
        item.session_id || item.sessionId || "",
        item.agent_id || item.agentId || "",
        unifiedTaskListText(text).toLowerCase(),
        item.channel_name || item.channelName || "",
      ].map(unifiedTaskListText).filter(Boolean).join("::");
    }

    function unifiedTaskListIsMeaningfulRoleText(text) {
      const value = unifiedTaskListText(text);
      if (!value) return false;
      if (/^[`~!@#$%^&*()_+\-=[\]{};:'",.<>/?\\|，。；：、“”‘’（）【】《》·…—\s]+$/.test(value)) return false;
      if (/^(?:主|执|协|管|验|审|位|责任位)$/.test(value)) return false;
      return true;
    }

    function unifiedTaskListRoleMembers(members) {
      const out = [];
      const seen = new Set();
      (Array.isArray(members) ? members : []).forEach((member) => {
        if (!member) return;
        const text = unifiedTaskListRoleMemberText(member);
        if (!unifiedTaskListIsMeaningfulRoleText(text)) return;
        const key = unifiedTaskListRoleMemberKey(member, text) || text;
        if (seen.has(key)) return;
        seen.add(key);
        out.push(member);
      });
      return out;
    }

    function unifiedTaskListRoleGroups(model) {
      const roles = model && model.roles ? model.roles : null;
      if (!roles) return null;
      const maxVisible = 5;
      let visibleLeft = maxVisible;
      let hiddenCount = 0;
      const groups = [
        { label: "主", members: roles.main_owner ? [roles.main_owner] : [] },
        { label: "执", members: Array.isArray(roles.executors) ? roles.executors : [] },
        { label: "管", members: Array.isArray(roles.management_slot) ? roles.management_slot : [] },
        { label: "验", members: Array.isArray(roles.validators) ? roles.validators : [] },
        { label: "审", members: Array.isArray(roles.user_reviewers) ? roles.user_reviewers : [] },
      ];
      const wrap = el("div", { class: "unified-task-list-roles" });
      groups.forEach((group) => {
        const allMembers = unifiedTaskListRoleMembers(group.members);
        if (!allMembers.length) return;
        const members = visibleLeft > 0 ? allMembers.slice(0, visibleLeft) : [];
        hiddenCount += Math.max(0, allMembers.length - members.length);
        visibleLeft = Math.max(0, visibleLeft - members.length);
        if (!members.length) return;
        const block = el("div", { class: "unified-task-list-role-group" });
        block.appendChild(el("span", { class: "unified-task-list-role-label", text: group.label }));
        const avatars = el("div", { class: "unified-task-list-role-avatars" });
        members.forEach((member) => {
          const avatar = typeof buildTaskRoleAvatar === "function"
            ? buildTaskRoleAvatar(member, { avatarClassName: "unified-task-list-avatar" })
            : el("span", {
                class: "unified-task-list-avatar",
                text: unifiedTaskListText(member && (member.display_name || member.name || member.alias)).slice(0, 1) || group.label,
              });
          if (avatar) avatars.appendChild(avatar);
        });
        if (avatars.childNodes.length) {
          block.appendChild(avatars);
          wrap.appendChild(block);
        }
      });
      if (hiddenCount > 0) {
        wrap.appendChild(el("span", { class: "unified-task-list-role-more", text: "+" + hiddenCount }));
      }
      return wrap.childNodes.length ? wrap : null;
    }

    function unifiedTaskListInteractiveTarget(target) {
      return !!(target && typeof target.closest === "function" && target.closest("button,a,input,textarea,select,label,summary,details"));
    }

    function bindUnifiedTaskListOpen(card, item, opts = {}) {
      const onOpen = typeof opts.onOpen === "function" ? opts.onOpen : null;
      if (!card || !onOpen) return;
      card.classList.add("is-clickable");
      card.tabIndex = 0;
      card.setAttribute("role", "button");
      card.addEventListener("click", (event) => {
        if (unifiedTaskListInteractiveTarget(event.target)) return;
        event.preventDefault();
        onOpen(item);
      });
      card.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        onOpen(item);
      });
    }

    function buildUnifiedTaskListCard(raw, opts = {}) {
      const item = (raw && typeof raw === "object") ? raw : {};
      const context = {
        source: opts.source || "task-list",
        projectId: opts.projectId,
        projectName: opts.projectName,
        channelName: opts.channelName,
        groupTitle: opts.groupTitle,
        forceTaskType: opts.forceTaskType,
      };
      const model = typeof unifiedTaskDetailModelFromTaskItem === "function"
        ? unifiedTaskDetailModelFromTaskItem(item, context)
        : {
            title: unifiedTaskListText(item.title || item.task_title || item.taskTitle || item.path || "未命名任务"),
            typeKey: opts.forceTaskType || "parent",
            statusText: unifiedTaskListText(item.task_primary_status || item.status || "待办"),
            groupTitle: unifiedTaskListText(opts.groupTitle || item.__groupTitle || ""),
            summaryText: unifiedTaskListText(item.summary || item.task_summary_text || ""),
            latestActionText: unifiedTaskListText(item.latest_action_text || item.latestActionText || ""),
            latestActionAt: unifiedTaskListText(item.latest_action_at || item.latestActionAt || item.updated_at || ""),
            taskPath: unifiedTaskListText(item.task_path || item.taskPath || item.path || ""),
            roles: null,
          };
      const typeKey = String(opts.forceTaskType || model.typeKey || "parent") === "child" ? "child" : "parent";
      const card = el("div", {
        class: [
          "unified-task-list-card",
          typeKey === "child" ? "is-child" : "is-parent",
          opts.compact ? "is-compact" : "",
          opts.panel ? "is-panel" : "",
          opts.active ? "active" : "",
        ].filter(Boolean).join(" "),
        "data-path": unifiedTaskListText(model.taskPath || item.path || item.task_path),
      });

      const top = el("div", { class: "unified-task-list-top" });
      const typeChip = el("span", {
        class: "unified-task-list-type is-" + typeKey,
        text: unifiedTaskListTypeLabel(typeKey),
      });
      top.appendChild(typeChip);
      top.appendChild(chip(model.statusText || "待办", unifiedTaskListTone(model.statusText)));
      if (model.groupTitle) top.appendChild(chip(model.groupTitle, "muted"));
      card.appendChild(top);

      const main = el("div", { class: "unified-task-list-main" });
      main.appendChild(el("div", {
        class: "unified-task-list-title",
        text: model.title || "未命名任务",
        title: model.taskPath || model.title || "",
      }));
      const latest = unifiedTaskListText(
        opts.latestText
        || model.latestActionText
        || model.summaryText
        || (opts.fallbackText || "")
      );
      if (latest) {
        main.appendChild(el("div", { class: "unified-task-list-latest", text: latest }));
      }
      card.appendChild(main);

      const roles = unifiedTaskListRoleGroups(model);
      if (roles) card.appendChild(roles);

      const meta = el("div", { class: "unified-task-list-meta" });
      const metaItems = Array.isArray(opts.metaItems) ? opts.metaItems : [];
      metaItems.forEach((entry) => {
        const text = unifiedTaskListText(Array.isArray(entry) ? entry[0] : entry);
        if (!text) return;
        const tone = Array.isArray(entry) ? (entry[1] || "muted") : "muted";
        meta.appendChild(chip(text, tone));
      });
      const channelText = unifiedTaskListText(opts.channelName || item.channel_name || item.channelName || item.channel);
      if (channelText) meta.appendChild(chip(channelText, "muted"));
      const updatedText = unifiedTaskListTime(opts.updatedAt || item.updated_at || item.latest_action_at || item.latestActionAt);
      if (updatedText) meta.appendChild(chip("更新 " + updatedText, "muted"));
      if (meta.childNodes.length) card.appendChild(meta);

      const foot = el("div", { class: "unified-task-list-foot" });
      (Array.isArray(opts.actions) ? opts.actions : []).forEach((node) => {
        if (node) foot.appendChild(node);
      });
      if (foot.childNodes.length) card.appendChild(foot);

      bindUnifiedTaskListOpen(card, item, opts);
      return card;
    }

    function buildUnifiedTaskChildGrid(children, buildChild) {
      const grid = el("div", { class: "unified-task-child-grid" });
      const rows = Array.isArray(children) ? children : [];
      if (!rows.length) {
        grid.appendChild(el("div", { class: "unified-task-child-empty", text: "当前没有可展示子任务。" }));
        return grid;
      }
      rows.forEach((child) => {
        const node = typeof buildChild === "function" ? buildChild(child) : null;
        if (node) grid.appendChild(node);
      });
      return grid;
    }
