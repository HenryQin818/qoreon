<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Qoreon · 项目总览</title>
  <style>__INLINE_CSS__</style>
</head>
<body>
  <div class="shell">
    <header class="head" id="header">
      <div class="head-left">
        <div class="brand-row">
          <h1 class="title" id="title">Qoreon</h1>
          <a class="official-site-link" id="officialSiteLink" href="https://qoreon.com" target="_blank" rel="noopener noreferrer" title="打开 Qoreon 官网" aria-label="打开 Qoreon 官网">
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.8"/>
              <path d="M3.6 9h16.8M3.6 15h16.8M12 3c2.1 2.4 3.2 5.4 3.2 9s-1.1 6.6-3.2 9M12 3c-2.1 2.4-3.2 5.4-3.2 9s1.1 6.6 3.2 9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
            <span>官网</span>
          </a>
        </div>
        <p class="sub" id="sub" hidden></p>
      </div>
      <div class="head-actions">
        <button class="btn btn-primary" id="newProjectBtn" type="button">新增项目</button>
        <button class="btn btn-ghost" id="agentCurtainBtn" type="button">消息瀑布</button>
        <button class="btn btn-ghost btn-with-tag" id="agentRelationshipBoardBtn" type="button">
          <span>组织战略</span>
          <span class="btn-tag-new">NEW</span>
        </button>
        <button class="btn btn-ghost" id="worklogBtn" type="button">平台文章</button>
        <button class="btn btn-ghost" id="configBtn" type="button">配置</button>
      </div>
    </header>

    <nav class="ctrlbar" id="controls" aria-label="控制栏">
      <div class="ctrl-left">
        <div class="search-filter-group" id="projectFilterWrap">
          <input class="input" id="q" placeholder="搜索项目..." />
          <button class="btn btn-ghost filter-btn" id="projectFilterBtn" type="button" title="项目筛选" aria-label="项目筛选">
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M4 6h16M7 12h10M10 18h4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
            </svg>
          </button>
          <div class="project-filter-pop" id="projectFilterPop" hidden>
            <div class="project-filter-title">项目筛选</div>
            <div class="project-filter-list" id="projectFilterList"></div>
            <div class="project-filter-actions">
              <button class="btn btn-ghost" id="projectFilterAllBtn" type="button">全选</button>
              <button class="btn btn-ghost" id="projectFilterClearBtn" type="button">清空</button>
              <button class="btn btn-primary" id="projectFilterApplyBtn" type="button">确认</button>
            </div>
          </div>
        </div>
        <button class="btn btn-ghost" id="sortBtn" type="button">按优先级</button>
        <button class="btn btn-ghost" id="statsBtn" type="button">隐藏统计</button>
      </div>
      <div class="ctrl-meta" id="meta"></div>
    </nav>

    <div id="listView">
      <section class="stats-container" id="stats" aria-label="统计概览"></section>
      <section class="cards-grid" id="cards" aria-label="项目列表"></section>
    </div>

    <div id="graphView" hidden>
      <div class="graph-top-left">
        <button class="btn btn-icon" id="graphBackBtn" title="返回列表">←</button>
        <button class="btn btn-icon" id="graphMenuBtn" title="菜单">☰</button>
      </div>
      <section class="graph-roster-board" id="graphRosterBoard" hidden>
        <header class="graph-roster-head">项目 Agent</header>
        <div class="graph-roster-list" id="graphRosterList">
          <div class="agent-empty">暂无 Agent</div>
        </div>
      </section>

      <aside class="graph-drawer left" id="graphSidebar" hidden>
        <div class="graph-panel">
          <h3>筛选</h3>
          <label class="graph-filter"><input type="checkbox" checked data-filter="project"> 项目区域</label>
          <label class="graph-filter"><input type="checkbox" checked data-filter="channel"> 通道塔台</label>
          <label class="graph-filter"><input type="checkbox" checked data-filter="agent"> Agent</label>
          <label class="graph-filter"><input type="checkbox" checked data-filter="run"> 运行事件</label>
          <label class="graph-filter"><input type="checkbox" checked data-filter="task"> 任务文档</label>
          <label class="graph-filter"><input type="checkbox" checked data-filter="feedback"> 反馈记录</label>
          <label class="graph-filter"><input type="checkbox" data-filter="risk"> 仅显示高风险</label>
          <label class="graph-filter"><input type="checkbox" data-filter="active_agents"> 仅显示活跃Agent</label>
          <label class="graph-filter"><input type="checkbox" data-filter="support_low"> 仅看支撑不足</label>
          <label class="graph-filter"><input type="checkbox" data-filter="assist_in_progress"> 仅看协助中</label>
          <label class="graph-filter"><input type="checkbox" data-filter="assist_waiting_reply"> 仅看待回复</label>
          <label class="graph-filter"><input type="checkbox" data-filter="assist_closed"> 仅看已收口</label>
        </div>
        <div class="graph-panel">
          <h3>Agent 状态</h3>
          <div class="agent-hint" style="color:#94a3b8;font-size:12px;padding:4px 0;">Agent 名录见左侧项目墙</div>
        </div>
        <div class="graph-panel">
          <h3>图例</h3>
          <div class="legend-item"><span class="dot project"></span> 项目 (Project)</div>
          <div class="legend-item"><span class="dot channel"></span> 通道 (Channel)</div>
          <div class="legend-item"><span class="dot agent"></span> Agent</div>
          <div class="legend-item"><span class="dot run"></span> 运行 (Run)</div>
          <div class="legend-item"><span class="dot task"></span> 任务 (Task)</div>
          <div class="legend-item"><span class="dot feedback"></span> 反馈 (Feedback)</div>
        </div>
      </aside>
      
      <main class="graph-stage">
        <div class="graph-hud">
          <div class="graph-hud-top">
            <div class="hud-stats" id="graphStats"></div>
            <button class="btn btn-ghost hud-btn" id="timelineBtn">
              <span class="icon">⏱</span> 时间轴
            </button>
          </div>
          <div class="graph-task-status-bar" id="graphTaskStatusBar">
            <div class="task-status-filters task-status-top" id="taskStatusFilters">
              <div class="agent-hint">当前项目暂无任务状态</div>
            </div>
          </div>
        </div>
        <canvas id="graphCanvas"></canvas>
        <div class="wall-controls" id="wallControls">
          <button class="btn btn-icon" id="wallZoomInBtn">＋</button>
          <button class="btn btn-icon" id="wallZoomOutBtn">－</button>
          <button class="btn btn-icon" id="wallZoomResetBtn">⟲</button>
        </div>
        <div class="graph-controls">
          <button class="btn btn-icon" id="zoomInBtn">+</button>
          <button class="btn btn-icon" id="zoomOutBtn">-</button>
          <button class="btn btn-icon" id="resetCamBtn">⟲</button>
        </div>
      </main>

      <aside class="graph-drawer right" id="graphDetails" hidden>
        <div class="details-empty">点击节点查看详情</div>
        <div class="details-content" hidden>
          <header class="details-header">
            <div class="details-type" id="dType">TYPE</div>
            <h2 class="details-title" id="dTitle">Title</h2>
            <div class="details-subtitle" id="dSub">Subtitle</div>
          </header>
          <div class="details-body" id="dBody"></div>
          <div class="details-actions" id="dActions"></div>
        </div>
      </aside>

      <aside class="timeline-drawer" id="timelineDrawer" hidden>
        <header class="timeline-header">
          <div class="timeline-title">Agent 工作时间轴</div>
          <div class="timeline-controls">
            <div class="timeline-filters">
              <span class="filter-label">窗口:</span>
              <button class="t-btn active" data-win="24h">24h</button>
              <button class="t-btn" data-win="3d">3d</button>
              <button class="t-btn" data-win="7d">7d</button>
            </div>
            <div class="timeline-filters">
              <span class="filter-label">状态:</span>
              <label><input type="checkbox" checked data-status="running"> 运行中</label>
              <label><input type="checkbox" checked data-status="queued"> 排队</label>
              <label><input type="checkbox" checked data-status="done"> 完成</label>
              <label><input type="checkbox" checked data-status="error"> 异常</label>
            </div>
            <button class="btn btn-icon" id="timelineCloseBtn">✕</button>
          </div>
        </header>
        <div class="timeline-body">
          <div class="timeline-freq-chart" id="timelineFreq"></div>
          <div class="timeline-gantt-container" id="timelineGantt"></div>
        </div>
      </aside>
    </div>
  </div>

  <div class="cfg-mask" id="cfgMask" hidden></div>
  <aside class="cfg-drawer" id="cfgDrawer" aria-hidden="true" aria-label="配置中心">
    <header class="cfg-head">
      <div>
        <h2 class="cfg-title">配置中心</h2>
        <p class="cfg-subtitle">总揽页可直接调整运行配置（V1）</p>
      </div>
      <button class="btn btn-ghost" id="cfgCloseBtn" type="button">关闭</button>
    </header>

    <section class="cfg-section">
      <h3>全局运行</h3>
      <label class="cfg-field">
        <span>并发上限（1-32）</span>
        <input class="input" id="cfgMaxConcurrency" type="number" min="1" max="32" />
      </label>
      <p class="cfg-hint" id="cfgGlobalHint">修改后需重启本机服务生效</p>
      <button class="btn btn-primary cfg-btn" id="cfgSaveGlobalBtn" type="button">保存全局配置</button>
    </section>

    <section class="cfg-section">
      <h3>平台状态（只读）</h3>
      <div class="cfg-kv"><span>服务绑定</span><code id="cfgBind">-</code></div>
      <div class="cfg-kv"><span>调度引擎</span><code id="cfgSchedulerEngine">-</code></div>
      <div class="cfg-kv"><span>Token校验</span><code id="cfgTokenRequired">-</code></div>
      <div class="cfg-kv"><span>本机覆盖配置</span><code id="cfgWithLocalConfig">-</code></div>
    </section>

    <section class="cfg-section">
      <h3>CLI 联通</h3>
      <p class="cfg-hint" id="cfgCliSummary">-</p>
      <p class="cfg-hint" id="cfgCliBinsHint">本机明文配置；留空时自动发现。</p>
      <div class="cfg-cli-list" id="cfgCliList"></div>
      <button class="btn btn-primary cfg-btn" id="cfgSaveCliBinsBtn" type="button">保存 CLI 路径</button>
    </section>

    <section class="cfg-section">
      <h3>快捷入口</h3>
      <div class="cfg-link-card">
        <div class="cfg-link-title">头像库管理</div>
        <p class="cfg-link-desc">统一维护 Agent 头像分配，可用于会话列表和组织视图识别。</p>
        <code class="cfg-link-url" id="cfgAvatarLibraryUrl">-</code>
        <div class="cfg-link-actions">
          <button class="btn btn-ghost cfg-btn" id="cfgOpenAvatarLibraryBtn" type="button">打开页面</button>
          <button class="btn btn-ghost cfg-btn" id="cfgCopyAvatarLibraryBtn" type="button">复制链接</button>
        </div>
      </div>
    </section>

    <p class="cfg-message" id="cfgMessage"></p>
  </aside>

  <div class="cfg-mask worklog-mask" id="worklogMask" hidden></div>
  <aside class="cfg-drawer worklog-drawer" id="worklogDrawer" aria-hidden="true" aria-label="平台文章">
    <header class="cfg-head">
      <div>
        <h2 class="cfg-title">平台文章</h2>
      </div>
      <button class="btn btn-ghost" id="worklogCloseBtn" type="button">关闭</button>
    </header>
    <div class="worklog-list" id="worklogList"></div>
  </aside>

  <div class="cfg-mask project-bootstrap-mask" id="projectBootstrapMask" hidden></div>
  <aside class="cfg-drawer project-bootstrap-drawer" id="projectBootstrapDrawer" aria-hidden="true" aria-label="新增项目">
    <header class="cfg-head">
      <div>
        <h2 class="cfg-title">新增项目</h2>
        <p class="cfg-subtitle">首页只负责采集项目基础信息，并展示创建结果。</p>
      </div>
      <button class="btn btn-ghost" id="projectBootstrapCloseBtn" type="button">关闭</button>
    </header>

    <section class="cfg-section">
      <h3>项目基础</h3>
      <p class="cfg-hint">只需填写最少信息即可创建项目，高级配置默认收纳在下方。</p>
      <div class="project-bootstrap-grid project-bootstrap-grid-basic">
        <label class="cfg-field">
          <span>项目 ID</span>
          <input class="input" id="projectBootstrapProjectId" type="text" placeholder="demo_project" autocomplete="off" />
        </label>
        <label class="cfg-field">
          <span>项目名称</span>
          <input class="input" id="projectBootstrapProjectName" type="text" placeholder="演示项目" autocomplete="off" />
        </label>
      </div>
      <label class="cfg-field">
        <span>项目说明（可选）</span>
        <textarea class="project-bootstrap-textarea" id="projectBootstrapDescription" rows="4" placeholder="说明项目背景、目标或接入边界。"></textarea>
      </label>
    </section>

    <section class="cfg-section project-bootstrap-advanced-wrap">
      <details class="project-bootstrap-advanced" id="projectBootstrapAdvanced">
        <summary class="project-bootstrap-advanced-summary">
          <span>高级配置（可选）</span>
          <span class="project-bootstrap-advanced-summary-hint">目录、分工与执行选项</span>
        </summary>
        <div class="project-bootstrap-advanced-body">
          <div class="project-bootstrap-advanced-block">
            <h3>目录与环境</h3>
            <p class="cfg-hint">以下路径都相对当前 `task-dashboard` 仓库根目录填写，默认按项目 ID 自动生成。</p>
            <div class="project-bootstrap-grid">
              <label class="cfg-field">
                <span>项目根目录（自动）</span>
                <input class="input" id="projectBootstrapProjectRoot" type="text" placeholder="projects/demo_project" autocomplete="off" readonly />
              </label>
              <label class="cfg-field">
                <span>任务根目录（自动）</span>
                <input class="input" id="projectBootstrapTaskRoot" type="text" placeholder="projects/demo_project/任务规划" autocomplete="off" readonly />
              </label>
              <label class="cfg-field">
                <span>主题色</span>
                <input class="input" id="projectBootstrapColor" type="text" placeholder="#0F63F2" autocomplete="off" />
              </label>
              <label class="cfg-field">
                <span>执行权限</span>
                <select class="input" id="projectBootstrapProfile">
                  <option value="project_privileged_full">project_privileged_full</option>
                  <option value="sandboxed">sandboxed</option>
                </select>
              </label>
              <label class="cfg-field">
                <span>环境</span>
                <select class="input" id="projectBootstrapEnvironment">
                  <option value="stable">stable</option>
                  <option value="dev">dev</option>
                </select>
              </label>
            </div>
          </div>

          <div class="project-bootstrap-advanced-block">
            <h3>默认分工（固定）</h3>
            <p class="cfg-hint">创建后固定仅保留 1 条总控分工，不支持新增、移除或改名。</p>
            <div class="project-bootstrap-channel-list" id="projectBootstrapChannelList"></div>
          </div>

          <div class="project-bootstrap-advanced-block">
            <h3>执行选项</h3>
            <label class="cfg-check">
              <input id="projectBootstrapCreatePrimarySessions" type="checkbox" checked />
              自动初始化主会话
            </label>
            <label class="cfg-check">
              <input id="projectBootstrapGenerateRegistry" type="checkbox" checked />
              生成通讯录与目录产物
            </label>
            <label class="cfg-check">
              <input id="projectBootstrapRunVisibilityCheck" type="checkbox" checked />
              执行可见性校验
            </label>
          </div>
        </div>
      </details>
    </section>

    <section class="cfg-section">
      <div class="project-bootstrap-toolbar">
        <div>
          <h3>创建结果</h3>
          <p class="cfg-hint">会展示返回状态、关键路径、初始化会话与步骤结果。</p>
        </div>
        <button class="btn btn-ghost cfg-btn" id="projectBootstrapReloadBtn" type="button" hidden>刷新总览</button>
      </div>
      <div class="project-bootstrap-result" id="projectBootstrapResult"></div>
    </section>

    <div class="project-bootstrap-actions">
      <div class="cfg-message" id="projectBootstrapMessage"></div>
      <div class="project-bootstrap-action-buttons">
        <button class="btn btn-ghost" id="projectBootstrapResetBtn" type="button">重置表单</button>
        <button class="btn btn-primary" id="projectBootstrapSubmitBtn" type="button">创建项目</button>
      </div>
    </div>
  </aside>

  <div class="cfg-mask project-cover-mask" id="projectCoverMask" hidden></div>
  <aside class="cfg-drawer project-cover-drawer" id="projectCoverDrawer" aria-hidden="true" aria-label="项目配图">
    <header class="cfg-head">
      <div>
        <h2 class="cfg-title">项目配图库</h2>
        <p class="cfg-subtitle" id="projectCoverSubtitle">为项目选择封面配图，默认按项目随机稳定分配。</p>
      </div>
      <button class="btn btn-ghost" id="projectCoverCloseBtn" type="button">关闭</button>
    </header>
    <section class="cfg-section">
      <h3 id="projectCoverProjectName">-</h3>
      <p class="cfg-hint">点击任一配图立即应用。你也可以上传办公类图片，上传后会自动加入图库并可随时切换。</p>
      <div class="project-cover-grid" id="projectCoverGrid"></div>
      <div class="project-cover-actions">
        <div class="project-cover-actions-left">
          <input id="projectCoverUploadInput" type="file" accept="image/*" hidden />
          <button class="btn btn-ghost" id="projectCoverUploadBtn" type="button">上传自定义图片</button>
        </div>
        <div class="project-cover-actions-right">
          <button class="btn btn-ghost" id="projectCoverResetBtn" type="button">恢复默认随机</button>
        </div>
      </div>
    </section>
    <p class="cfg-message" id="projectCoverMessage"></p>
  </aside>

  <script id="data" type="application/json">__PAYLOAD__</script>
  <script>__INLINE_JS__</script>
  <script>
    (() => {
      const btn = document.getElementById("agentRelationshipBoardBtn");
      const payload = JSON.parse(document.getElementById("data")?.textContent || "{}");
      const links = (payload && payload.links && typeof payload.links === "object") ? payload.links : {};
      if (!btn) return;
      btn.addEventListener("click", () => {
        const base = String(payload.agent_relationship_board_page || links.agent_relationship_board_page || "/share/project-agent-relationship-board.html").trim();
        if (!base) return;
        try {
          const url = new URL(base, window.location.href);
          const hash = new URLSearchParams((url.hash || "").replace(/^#/, ""));
          hash.set("mode", "platform");
          url.hash = hash.toString();
          window.open(url.toString(), "_blank", "noopener,noreferrer");
        } catch (_) {
          const suffix = base.includes("#") ? "&mode=platform" : "#mode=platform";
          window.open(base + suffix, "_blank", "noopener,noreferrer");
        }
      });
    })();
  </script>
</body>
</html>
