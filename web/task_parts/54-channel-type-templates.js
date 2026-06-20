    const NEW_CHANNEL_TYPE_ORDER = [
      "总控",
      "助理",
      "产品",
      "镜像",
      "前端",
      "后端",
      "测试",
      "服务",
      "通讯",
      "任务",
      "技能",
      "资料",
      "视觉",
    ];

    const NEW_CHANNEL_TYPE_TEMPLATES = {
      "总控": {
        agentRole: "coordinator",
        standardRole: "总控",
        roleSummary: "范围冻结、跨通道调度、最终裁定、验收收口。",
        skills: ["task-workflow-create-validate", "collab-message-send", "project-startup-blueprint-gate"],
        workdir: "默认进入项目根目录；跨通道动作先确认责任位和验收口径。",
        guardrails: ["不放行服务动作", "不代替验收结论", "不伪造送达证据"],
        focus: ["先冻结目标、边界和不做项。", "跨 Agent 派发必须保留回执链路。", "收口时区分业务完成、消息送达和测试通过。"],
      },
      "助理": {
        agentRole: "planner",
        standardRole: "项目助理",
        roleSummary: "项目资料整理、异常协调、跨通道提醒、轻量跟进。",
        skills: ["collab-message-send", "codex-agent-collaboration", "task-workflow-create-validate"],
        workdir: "默认进入对应通道目录；只维护资料、提醒和轻量协调产出。",
        guardrails: ["不替主负责位裁定", "不自行扩题", "不写临时授权"],
        focus: ["先整理事实和待办，再请求责任位处理。", "提醒类消息要说明来源、目标和下一步。", "只把稳定规则写入 AGENTS.md。"],
      },
      "产品": {
        agentRole: "planner",
        standardRole: "产品规划",
        roleSummary: "需求收敛、产品方案、交互规格、任务拆解。",
        skills: ["assist04-requirement-intake-gate", "prototype-requirement-planning-flow", "task-workflow-create-validate"],
        workdir: "默认进入需求或方案通道目录；材料沉淀到产出物/材料或产出物/沉淀。",
        guardrails: ["不把草稿当冻结规格", "不跳过验收口径", "不直接改服务配置"],
        focus: ["先说明用户目标、输入输出和不做项。", "方案冻结后再派发执行位。", "验收口径要能被测试位复核。"],
      },
      "镜像": {
        agentRole: "planner",
        standardRole: "用户镜像",
        roleSummary: "用户视角、误解风险、价值判断、业务偏差提醒。",
        skills: ["visual-requirement-review-board", "product-interface-planning-guardrails", "collab-message-send"],
        workdir: "默认进入镜像通道目录；输出以观察、风险和用户体验判断为主。",
        guardrails: ["不替研发实现", "不替测试验收", "不把主观判断写成事实"],
        focus: ["优先指出用户能否理解、是否会误操作。", "把风险说成可验收的场景。", "保留用户视角，不扩成工程任务。"],
      },
      "前端": {
        agentRole: "developer",
        standardRole: "前端执行",
        roleSummary: "页面交互、前端实现、UI 状态、页面体验验证。",
        skills: ["product-interface-planning-guardrails", "task-dashboard-visual-refinement-support", "visual-requirement-review-board"],
        workdir: "默认进入前端通道目录；实现优先限定在 web/task、web/overview 相关文件。",
        guardrails: ["不改 API 语义", "不触发服务重启", "不扩大写入范围"],
        focus: ["先读现有交互和状态来源。", "做最小可验证改造，并补定向 UI 逻辑测试。", "说明是否需要服务管理另行重启。"],
      },
      "后端": {
        agentRole: "developer",
        standardRole: "后端执行",
        roleSummary: "API、读写模型、运行时、安全、并发、适配器。",
        skills: ["task-workflow-create-validate", "heartbeat-task-control", "codex-session-health-inspector"],
        workdir: "默认进入后端或运行时通道目录；修改 API 时同步契约和测试。",
        guardrails: ["不绕过 127.0.0.1 默认监听", "不放松 token 校验", "不直接启动生产服务"],
        focus: ["先确认契约和兼容字段。", "新增写入必须有边界校验。", "并发、调度或 API 改动必须补测试。"],
      },
      "测试": {
        agentRole: "tester",
        standardRole: "测试验收",
        roleSummary: "测试计划、验收矩阵、回归、live 验收。",
        skills: ["task-workflow-create-validate", "visual-requirement-review-board", "collab-message-send"],
        workdir: "默认进入测试通道目录；证据优先写清命令、结果和失败复现条件。",
        guardrails: ["不复用修复前证据", "不把未测项写成通过", "不执行发布动作"],
        focus: ["按冻结验收口径建立矩阵。", "覆盖正常、缺失、错误和边界状态。", "失败时给出影响范围和停止线。"],
      },
      "服务": {
        agentRole: "developer",
        standardRole: "服务管理",
        roleSummary: "启动、重启、注册、健康、service monitor 门禁。",
        skills: ["local-service-hub", "heartbeat-task-control", "codex-session-health-inspector"],
        workdir: "默认进入服务管理通道目录；真实服务动作必须另有 action_scope。",
        guardrails: ["不默认重启", "不默认发布", "不绕过服务管理门禁"],
        focus: ["先做只读健康和影响判断。", "服务动作必须有授权、回滚和验收清单。", "service monitor 变更要单独留证。"],
      },
      "通讯": {
        agentRole: "coordinator",
        standardRole: "通讯治理",
        roleSummary: "消息模式、送达证据、通讯录、回执链路。",
        skills: ["collab-message-send", "codex-agent-collaboration", "webtag-ccb-bridge"],
        workdir: "默认进入通讯通道目录；所有正式消息只认 announce 证据链。",
        guardrails: ["不把草稿当通知", "不借用他人身份", "不伪造 announce_run_id"],
        focus: ["先判定 dialog/task/notify 模式。", "发送后核验 target_session_id 和 visible_in_channel_chat。", "目标不可达时回阻塞，不手工绕过。"],
      },
      "任务": {
        agentRole: "coordinator",
        standardRole: "任务管理",
        roleSummary: "任务创建、责任位、派发、验收、归档收口。",
        skills: ["task-workflow-create-validate", "sub05-issue-aggregation", "collab-message-send"],
        workdir: "默认进入任务治理通道目录；任务推进以任务文件和责任位为真源。",
        guardrails: ["不散装手写责任位", "不跳过 announce 证据", "不批量改写历史任务"],
        focus: ["创建任务先补 Harness 责任位。", "派发、验收和完成分别校验证据。", "问题类告警按聚合规则治理。"],
      },
      "技能": {
        agentRole: "coordinator",
        standardRole: "技能治理",
        roleSummary: "skills 创建、审核、升级、冲突治理。",
        skills: ["project-skill-maintenance", "skill-creator", "collab-message-send"],
        workdir: "默认进入技能治理通道目录；技能只写触发口径和执行边界。",
        guardrails: ["不把 skill 当授权", "不覆盖项目规则", "不引入冲突触发"],
        focus: ["先确认现有技能是否可复用。", "新技能必须说明触发、不触发和边界。", "升级后同步索引和最小验证。"],
      },
      "资料": {
        agentRole: "general",
        standardRole: "资料治理",
        roleSummary: "README、AGENTS、索引、项目资料真源维护。",
        skills: ["public-project-maintenance-architecture-canvas-doc", "nutstore-collab-doc", "collab-message-send"],
        workdir: "默认进入资料通道目录；只沉淀长期有效资料，不保存瞬时运行态。",
        guardrails: ["不写 token/PID/run_id", "不替代任务文件", "不批量覆盖历史资料"],
        focus: ["先区分真源、材料和沉淀。", "长期规则写 AGENTS.md，过程材料写产出物。", "资料更新要保留来源和适用范围。"],
      },
      "视觉": {
        agentRole: "planner",
        standardRole: "视觉设计",
        roleSummary: "视觉系统、设计一致性、可读性、页面审美审核。",
        skills: ["task-dashboard-visual-refinement-support", "visual-board-delivery-playbook", "visual-requirement-review-board"],
        workdir: "默认进入视觉通道目录；输出以页面可读性、信息密度和一致性为主。",
        guardrails: ["不改业务语义", "不替代前端实现", "不只给主观评价"],
        focus: ["先看结构、层级和信息密度。", "给出可执行的视觉调整点。", "移动端和极限数据要同步检查。"],
      },
    };

    function normalizeNewChannelTypeKey(raw) {
      const text = String(raw || "").trim();
      if (!text) return "";
      for (const key of NEW_CHANNEL_TYPE_ORDER) {
        if (text === key || text.startsWith(key)) return key;
      }
      return "";
    }

    function resolveNewChannelTypeTemplate(raw) {
      const key = normalizeNewChannelTypeKey(raw) || "产品";
      const template = NEW_CHANNEL_TYPE_TEMPLATES[key] || NEW_CHANNEL_TYPE_TEMPLATES["产品"];
      return { key, ...template };
    }

    function newChannelTypeList() {
      return NEW_CHANNEL_TYPE_ORDER.map((key) => ({ key, ...NEW_CHANNEL_TYPE_TEMPLATES[key] }));
    }

    function renderNewChannelTypeAgentsMdTemplate(form) {
      const data = resolveNewChannelTypeTemplate(form && form.channelKind);
      const name = String((form && form.channelFullName) || (typeof buildNewChannelName === "function" ? buildNewChannelName(form || {}) : "") || "新通道").trim();
      const desc = String((form && (form.channelDesc || form.channelName)) || "").trim() || "请在通道编辑页补充本通道的长期职责、边界和协作方式。";
      const focus = (Array.isArray(data.focus) ? data.focus : []).map((item) => "- " + item).join("\n");
      const skills = (Array.isArray(data.skills) ? data.skills : []).map((item) => "- `" + item + "`").join("\n");
      const guardrails = (Array.isArray(data.guardrails) ? data.guardrails : []).map((item) => "- " + item).join("\n");
      return [
        "# AGENTS.md - " + name,
        "",
        "## 通道快速卡",
        "",
        "- 通道类型：" + data.key,
        "- 标准角色：" + data.standardRole + "（" + data.roleSummary + "）",
        "- 通道说明：" + desc,
        "- 默认 workdir：" + data.workdir,
        "",
        "## 工作方式",
        "",
        focus,
        "",
        "## 推荐 skills",
        "",
        skills,
        "",
        "## 禁区与停线",
        "",
        guardrails,
        "- 不写 token、PID、端口、run_id、临时 session、一次性授权或瞬时 health。",
        "- 不通过本文件授予服务启动、重启、发布、SessionStore 手动改写或真实初始化消息权限。",
        "",
        "## 生效说明",
        "",
        "- 本文件只保存长期规则；已写入不等于已生效，已运行会话不会自动刷新上下文。",
        "- 复杂消息回到 `collab-message-send`；复杂任务回到 `task-workflow-create-validate`。",
        "- 遇到授权、服务动作、会话治理或目标不可达时，先回单一阻塞，不自行绕过。",
        "",
      ].join("\n");
    }

    function setNewChannelTypeText(id, value) {
      const node = document.getElementById(id);
      if (node) node.textContent = String(value || "-");
    }

    function syncNewChannelTypeTemplateUi(form) {
      const data = resolveNewChannelTypeTemplate(form && form.channelKind);
      const roleInput = document.getElementById("newChannelAgentRole");
      if (roleInput) roleInput.value = data.agentRole || "general";
      setNewChannelTypeText("newChannelTypeRole", data.standardRole + " - " + data.roleSummary);
      setNewChannelTypeText("newChannelTypeSkills", (data.skills || []).join(" / "));
      setNewChannelTypeText("newChannelTypeWorkdir", data.workdir);
      setNewChannelTypeText("newChannelTypeGuardrails", (data.guardrails || []).join(" / "));
    }

    function buildNewConvChannelTypeInheritanceText(channelName) {
      const data = resolveNewChannelTypeTemplate(channelName);
      if (!normalizeNewChannelTypeKey(channelName)) {
        return "继承摘要：项目 AGENTS.md + 通道 AGENTS.md；当前通道未命中新版 2 字类型，按通用协作规则处理。";
      }
      return "继承摘要：项目 AGENTS.md + 通道 AGENTS.md；标准角色：" + data.standardRole
        + "（" + data.roleSummary + "）；workdir：" + data.workdir;
    }
