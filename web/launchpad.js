(() => {
  const DATA = JSON.parse(document.getElementById("data").textContent || "{}");
  const LINKS = (DATA && DATA.links && typeof DATA.links === "object") ? DATA.links : {};
  const PROJECTS = Array.isArray(DATA.projects) ? DATA.projects : [];

  const titleEl = document.getElementById("title");
  const subtitleEl = document.getElementById("subtitle");
  const projectListEl = document.getElementById("projectList");
  const linkGridEl = document.getElementById("linkGrid");
  const quickActionsEl = document.getElementById("quickActions");
  const healthStatusEl = document.getElementById("healthStatus");
  const healthMetaEl = document.getElementById("healthMeta");
  const refreshHealthBtn = document.getElementById("refreshHealthBtn");

  function text(value, fallback = "") {
    const out = String(value || "").trim();
    return out || fallback;
  }

  function el(tag, attrs = {}, children = []) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([key, value]) => {
      if (key === "class") node.className = String(value || "");
      else if (key === "text") node.textContent = String(value || "");
      else node.setAttribute(key, String(value));
    });
    (children || []).forEach((child) => node.appendChild(child));
    return node;
  }

  function linkCard({ title, desc, href, badge = "" }) {
    const card = el("a", { class: "quick-link", href: href || "#" });
    card.appendChild(el("h3", { text: title }));
    if (badge) card.appendChild(el("div", { class: "badge", text: badge }));
    card.appendChild(el("p", { text: desc }));
    return card;
  }

  function projectCard(project) {
    const href = text(LINKS.task_page, "project-task-dashboard.html");
    const card = el("a", { class: "card", href });
    card.appendChild(el("div", { class: "card-top" }, [
      el("h3", { text: text(project.name, text(project.id, "未命名项目")) }),
      el("span", { class: "badge", text: text(project.id, "project") }),
    ]));
    card.appendChild(el("p", {
      text: text(project.description, "进入任务看板查看项目、通道、任务和会话。")
    }));
    card.appendChild(el("p", {
      class: "hint",
      text: `任务根目录：${text(project.task_root_rel || project.taskRootRel, "-")}`
    }));
    return card;
  }

  async function refreshHealth() {
    const healthPath = text(LINKS.health_path, "/__health");
    healthStatusEl.textContent = "检测中";
    healthStatusEl.style.color = "";
    healthMetaEl.textContent = "正在请求本地服务";
    try {
      const resp = await fetch(healthPath, { cache: "no-store" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const payload = await resp.json();
      const ok = Boolean(payload && payload.ok);
      healthStatusEl.textContent = ok ? "服务正常" : "服务异常";
      healthStatusEl.style.color = ok ? "var(--good)" : "var(--bad)";
      healthMetaEl.textContent = `project=${text(payload.project_id, "unknown")} · env=${text(payload.environment, "stable")}`;
    } catch (err) {
      healthStatusEl.textContent = "服务未就绪";
      healthStatusEl.style.color = "var(--warn)";
      healthMetaEl.textContent = text(err && err.message, "无法连接 /__health");
    }
  }

  function renderProjects() {
    projectListEl.innerHTML = "";
    PROJECTS.forEach((project) => projectListEl.appendChild(projectCard(project)));
  }

  function renderLinks() {
    const items = [
      {
        title: "任务看板",
        desc: "主工作页，查看项目、通道、任务和会话。",
        href: text(LINKS.task_page, "project-task-dashboard.html"),
        badge: "主入口"
      },
      {
        title: "项目总览",
        desc: "先看项目清单和整体结构。",
        href: text(LINKS.overview_page, "project-overview-dashboard.html")
      },
      {
        title: "状态报告",
        desc: "看当前状态、风险、进度和建议动作。",
        href: text(LINKS.status_report_page, "project-status-report.html")
      },
      {
        title: "会话健康",
        desc: "排查 session、Agent 和运行状态。",
        href: text(LINKS.session_health_page, "project-session-health-dashboard.html")
      }
    ];
    linkGridEl.innerHTML = "";
    items.forEach((item) => linkGridEl.appendChild(linkCard(item)));
  }

  function renderQuickActions() {
    const items = [
      {
        title: "健康检查",
        desc: "直接访问 /__health 确认服务状态。",
        href: text(LINKS.health_path, "/__health")
      },
      {
        title: "通信审计",
        desc: "查看协作消息、回执和链路。",
        href: text(LINKS.communication_page, "project-communication-audit.html")
      },
      {
        title: "Agent 名录",
        desc: "集中查看 Agent 和角色分工。",
        href: text(LINKS.agent_directory_page, "project-agent-directory.html")
      },
      {
        title: "关系看板",
        desc: "图视角查看项目、通道和 Agent 关系。",
        href: text(LINKS.agent_relationship_board_page, "project-agent-relationship-board.html")
      }
    ];
    quickActionsEl.innerHTML = "";
    items.forEach((item) => quickActionsEl.appendChild(linkCard(item)));
  }

  function initHeader() {
    const dashboard = (DATA && DATA.dashboard && typeof DATA.dashboard === "object") ? DATA.dashboard : {};
    titleEl.textContent = text(dashboard.title, "Qoreon 启动中转页");
    subtitleEl.textContent = text(
      dashboard.subtitle,
      "页面启动后先到这里，再进入任务看板、总览、状态报告和会话健康页。"
    );
  }

  refreshHealthBtn.addEventListener("click", refreshHealth);
  initHeader();
  renderProjects();
  renderLinks();
  renderQuickActions();
  refreshHealth();
})();
