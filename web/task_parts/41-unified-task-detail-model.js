    // Unified task detail read model. All entrypoints normalize here before rendering.
    const UNIFIED_TASK_DETAIL_ROLE_ORDER = Object.freeze([
      "main_owner",
      "executors",
      "management_slot",
      "validators",
      "user_reviewers",
    ]);

    function unifiedTaskDetailText(value) {
      return String(value == null ? "" : value).trim();
    }

    function unifiedTaskDetailFirstNonEmpty(values, fallback = "") {
      const list = Array.isArray(values) ? values : [values];
      if (typeof firstNonEmptyText === "function") {
        return unifiedTaskDetailText(firstNonEmptyText(list, fallback));
      }
      for (const item of list) {
        const text = unifiedTaskDetailText(item);
        if (text) return text;
      }
      return unifiedTaskDetailText(fallback);
    }

    function unifiedTaskDetailShortTitle(value) {
      const text = unifiedTaskDetailText(value);
      if (!text) return "未命名任务";
      if (typeof shortTitle === "function") return shortTitle(text) || text;
      return text.replace(/^(?:【[^】]+】\s*)+/u, "").replace(/\.md$/i, "").trim() || text;
    }

    function unifiedTaskDetailRoleMember(rawMember) {
      if (rawMember == null) return null;
      if (typeof rawMember === "string") {
        const text = unifiedTaskDetailText(rawMember);
        return text ? { display_name: text, name: text } : null;
      }
      if (typeof rawMember !== "object") return null;
      return { ...rawMember };
    }

    function unifiedTaskDetailRoleList(rawMembers) {
      const list = Array.isArray(rawMembers)
        ? rawMembers
        : (rawMembers == null ? [] : [rawMembers]);
      const seen = new Set();
      const out = [];
      list.forEach((member) => {
        const item = unifiedTaskDetailRoleMember(member);
        if (!item) return;
        const text = unifiedTaskDetailFirstNonEmpty([
          item.session_id,
          item.sessionId,
          item.agent_id,
          item.agentId,
          item.display_name,
          item.agent_alias,
          item.alias,
          item.agent_name,
          item.name,
        ], "");
        if (!text) return;
        const key = [
          unifiedTaskDetailText(item.session_id || item.sessionId),
          unifiedTaskDetailText(item.agent_id || item.agentId),
          unifiedTaskDetailText(item.display_name || item.agent_alias || item.alias || item.agent_name || item.name).toLowerCase(),
        ].filter(Boolean).join("::") || text.toLowerCase();
        if (seen.has(key)) return;
        seen.add(key);
        out.push(item);
      });
      return out;
    }

    function unifiedTaskDetailCustomRoleList(rawRoles) {
      const rows = Array.isArray(rawRoles) ? rawRoles : [];
      return rows.map((role) => {
        const item = (role && typeof role === "object") ? role : null;
        if (!item) return null;
        return {
          ...item,
          name: unifiedTaskDetailText(item.name || item.role_name || item.roleName),
          responsibility: unifiedTaskDetailText(item.responsibility),
          members: unifiedTaskDetailRoleList(item.members),
        };
      }).filter((role) => role && (role.name || role.members.length));
    }

    function unifiedTaskDetailIsUserReviewerRole(role) {
      const text = unifiedTaskDetailText([
        role && role.name,
        role && role.role_name,
        role && role.roleName,
        role && role.responsibility,
      ].join(" "));
      return /(?:用户审核|用户验收|用户确认|user[_\s-]?review|reviewer|acceptor)/i.test(text);
    }

    function unifiedTaskDetailResponsibilityModel(raw) {
      const item = (raw && typeof raw === "object") ? raw : {};
      const modelLike = item.responsibilityModel && typeof item.responsibilityModel === "object"
        ? item.responsibilityModel
        : (item.responsibility_model && typeof item.responsibility_model === "object"
          ? item.responsibility_model
          : item);
      const customRoles = unifiedTaskDetailCustomRoleList(modelLike.custom_roles || modelLike.customRoles);
      const userRoleMembers = [];
      customRoles.forEach((role) => {
        if (!unifiedTaskDetailIsUserReviewerRole(role)) return;
        role.members.forEach((member) => userRoleMembers.push(member));
      });
      const mainOwnerList = unifiedTaskDetailRoleList(modelLike.main_owner || modelLike.mainOwner);
      const model = {
        main_owner: mainOwnerList[0] || null,
        executors: unifiedTaskDetailRoleList(
          modelLike.executors
          || modelLike.execution_slot
          || modelLike.executionSlot
          || modelLike.collaborators
        ),
        management_slot: unifiedTaskDetailRoleList(modelLike.management_slot || modelLike.managementSlot),
        validators: unifiedTaskDetailRoleList(modelLike.validators),
        user_reviewers: unifiedTaskDetailRoleList(
          modelLike.user_reviewers
          || modelLike.userReviewers
          || modelLike.acceptors
          || userRoleMembers
        ),
      };
      model.hasData = !!(model.main_owner
        || model.executors.length
        || model.management_slot.length
        || model.validators.length
        || model.user_reviewers.length);
      return model;
    }

    function unifiedTaskDetailTypeKey(raw, context = {}) {
      const item = (raw && typeof raw === "object") ? raw : {};
      const forced = unifiedTaskDetailText(context.forceTaskType || item.task_role || item.taskRole).toLowerCase();
      if (forced === "child" || forced === "subtask") return "child";
      if (forced === "parent" || forced === "main" || forced === "master") return "parent";
      if (item._isSubtask === true || item.is_subtask === true || item.isSubtask === true) return "child";
      if (unifiedTaskDetailFirstNonEmpty([
        item.parent_task_id,
        item.parentTaskId,
        item.parent_task_path,
        item.parentTaskPath,
      ], "")) return "child";
      return "parent";
    }

    function unifiedTaskDetailStatus(raw) {
      const item = (raw && typeof raw === "object") ? raw : {};
      if (typeof resolveTaskPrimaryStatusText === "function") {
        return resolveTaskPrimaryStatusText(item.task_primary_status || item.primary_status || item.statusText || item.status || item, "待办");
      }
      return unifiedTaskDetailFirstNonEmpty([
        item.task_primary_status,
        item.primary_status,
        item.statusText,
        item.status,
      ], "待办");
    }

    function unifiedTaskDetailFacts(raw, context = {}) {
      const item = (raw && typeof raw === "object") ? raw : {};
      const rows = [
        ["项目", unifiedTaskDetailFirstNonEmpty([context.projectName, item.project_name, item.project_id, context.projectId], "")],
        ["通道", unifiedTaskDetailFirstNonEmpty([context.channelName, item.channel_name, item.channelName, item.channel], "")],
        ["所在分组", unifiedTaskDetailFirstNonEmpty([context.groupTitle, item.groupTitle, item.__groupTitle], "")],
        ["关联关系", unifiedTaskDetailFirstNonEmpty([item.relationLabel, item.relation_label, item.relation], "")],
        ["创建时间", unifiedTaskDetailFirstNonEmpty([item.createdAt, item.created_at], "")],
        ["截止时间", unifiedTaskDetailFirstNonEmpty([item.dueAt, item.due_at, item.due], "")],
        ["首次纳入", unifiedTaskDetailFirstNonEmpty([item.firstSeenAt, item.first_seen_at], "")],
        ["最近观察", unifiedTaskDetailFirstNonEmpty([item.lastSeenAt, item.last_seen_at], "")],
        ["任务路径", unifiedTaskDetailFirstNonEmpty([item.taskPath, item.task_path, item.path], "")],
      ];
      return rows
        .map(([label, value]) => ({ label, value: unifiedTaskDetailText(value) }))
        .filter((row) => row.value);
    }

    function normalizeUnifiedTaskDetailModel(raw, context = {}) {
      const item = (raw && typeof raw === "object") ? raw : {};
      const title = unifiedTaskDetailShortTitle(unifiedTaskDetailFirstNonEmpty([
        item.title,
        item.taskTitle,
        item.task_title,
        item.label,
        item.name,
        item.taskPath,
        item.task_path,
        item.path,
      ], "未命名任务"));
      const taskPath = unifiedTaskDetailFirstNonEmpty([
        item.taskPath,
        item.task_path,
        item.path,
      ], "");
      const taskId = unifiedTaskDetailFirstNonEmpty([
        item.taskId,
        item.task_id,
        item.id,
      ], "");
      const summaryText = unifiedTaskDetailFirstNonEmpty([
        item.taskSummaryText,
        item.task_summary_text,
        item.summary,
      ], "");
      const latestActionText = unifiedTaskDetailFirstNonEmpty([
        item.latestActionText,
        item.latest_action_text,
        item.action_text,
      ], "");
      return {
        version: "UnifiedTaskDetailModel.v1",
        source: unifiedTaskDetailText(context.source || item.source || "task"),
        taskId,
        taskPath,
        title,
        typeKey: unifiedTaskDetailTypeKey(item, context),
        statusText: unifiedTaskDetailStatus(item),
        groupTitle: unifiedTaskDetailFirstNonEmpty([context.groupTitle, item.groupTitle, item.__groupTitle], ""),
        relationLabel: unifiedTaskDetailFirstNonEmpty([item.relationLabel, item.relation_label, item.relation], ""),
        sourceText: unifiedTaskDetailFirstNonEmpty([item.sourceText, item.source], ""),
        summaryText,
        summaryPlaceholder: "任务一句话说明待接入正式真源。",
        latestActionText,
        latestActionAt: unifiedTaskDetailFirstNonEmpty([item.latestActionAt, item.latest_action_at, item.at], ""),
        latestActionKind: unifiedTaskDetailFirstNonEmpty([item.latestActionKind, item.latest_action_kind, item.action_kind], ""),
        latestActionSource: unifiedTaskDetailFirstNonEmpty([item.latestActionSource, item.latest_action_source, item.source_agent_name, item.source_channel], ""),
        roles: unifiedTaskDetailResponsibilityModel(item),
        facts: unifiedTaskDetailFacts(item, context),
        contextItems: Array.isArray(item.contextItems)
          ? item.contextItems.slice()
          : (Array.isArray(item.recent_task_actions) ? item.recent_task_actions.slice() : []),
        raw: item,
      };
    }

    function unifiedTaskDetailModelFromTaskItem(item, context = {}) {
      return normalizeUnifiedTaskDetailModel(item, {
        ...context,
        source: context.source || "task-panel",
      });
    }

    function unifiedTaskDetailModelFromConversationDetail(detail, context = {}) {
      return normalizeUnifiedTaskDetailModel(detail, {
        ...context,
        source: context.source || "conversation-task",
      });
    }

    function unifiedTaskDetailModelFromOverviewNode(node, context = {}) {
      return normalizeUnifiedTaskDetailModel(node, {
        ...context,
        source: context.source || "overview-task",
      });
    }
