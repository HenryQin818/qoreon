<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>消息瀑布 · Qoreon</title>
  <style>__INLINE_CSS__</style>
</head>
<body>
  <div class="page-shell">
    <section class="stage-panel">
      <div class="stage-toolbar">
        <div class="toolbar-row">
          <nav class="toolbar-left" aria-label="快捷入口">
            <a class="link-chip" id="overviewLink" href="/share/project-overview-dashboard.html">总揽</a>
            <a class="link-chip" id="taskLink" href="/share/project-task-dashboard.html">任务页</a>
            <button class="btn btn-ghost" id="refreshBtn" type="button">刷新</button>
            <span class="badge badge-readonly">只读</span>
            <span class="badge" id="envBadge">环境 -</span>
          </nav>
          <div class="toolbar-center" id="toolbarLegend" aria-label="关系线筛选">
            <span class="toolbar-group-label">关系线</span>
            <button class="legend-chip is-toggle is-active" data-link-type="dispatch" type="button" aria-pressed="true"><span class="dot dispatch"></span>派发线</button>
            <button class="legend-chip is-toggle is-active" data-link-type="reply" type="button" aria-pressed="true"><span class="dot reply"></span>回复线</button>
            <button class="legend-chip is-toggle is-active" data-link-type="system" type="button" aria-pressed="true"><span class="dot system"></span>系统线</button>
          </div>
          <div class="toolbar-right">
            <div class="chip-group" id="orderTabs" aria-label="Agent 排序">
              <span class="toolbar-group-label">排序</span>
              <button class="chip is-active" data-order="default" type="button">默认</button>
              <button class="chip" data-order="volume" type="button">消息量</button>
            </div>
            <div class="chip-group" id="windowTabs" aria-label="时间窗口">
              <button class="chip is-active" data-window="1h" type="button">1h</button>
              <button class="chip" data-window="6h" type="button">6h</button>
              <button class="chip" data-window="24h" type="button">24h</button>
              <button class="chip" data-window="custom" type="button">自定义</button>
            </div>
            <label class="toggle-chip"><input id="toggleLinks" type="checkbox" checked /> 显示关系线</label>
            <label class="toggle-chip"><input id="toggleSystem" type="checkbox" checked /> 系统消息</label>
            <label class="toggle-chip"><input id="toggleDone" type="checkbox" checked /> 终态消息</label>
          </div>
        </div>
        <div class="toolbar-meta">
          <span id="projectMeta">等待读取项目上下文</span>
          <span id="summaryMeta">Agent 0 · 事件 0 · 关系 0</span>
        </div>
        <div class="toolbar-custom" id="customRangeBar" hidden>
          <span class="custom-range-title">自定义时间</span>
          <label class="custom-range-field">
            <span>开始</span>
            <input id="customStartInput" type="datetime-local" />
          </label>
          <label class="custom-range-field">
            <span>结束</span>
            <input id="customEndInput" type="datetime-local" />
          </label>
          <button class="btn btn-ghost" id="customApplyBtn" type="button">应用</button>
          <button class="btn btn-ghost" id="customResetBtn" type="button">回到固定档</button>
        </div>
      </div>

      <div class="state-banner is-loading" id="stateBanner">正在加载消息瀑布...</div>

      <div class="stage-wrap" id="stageWrap" hidden>
        <div class="curtain-viewport" id="curtainViewport">
          <div class="curtain-sizer" id="curtainSizer">
            <div class="curtain" id="curtain">
              <div class="time-corner" id="timeCorner"></div>
              <div class="time-col" id="timeCol"></div>
              <div class="regions-layer" id="regionsLayer"></div>
              <div class="projects-layer" id="projectsLayer"></div>
              <div class="agent-heads-layer" id="agentHeadsLayer"></div>
              <div class="links-layer"><svg id="linksSvg" aria-hidden="true"></svg></div>
              <div class="agents-layer" id="agentsLayer"></div>
              <div class="events-layer" id="eventsLayer"></div>
            </div>
          </div>
        </div>
        <div class="zoom-dock" id="zoomDock">
          <div class="zoom-controls" aria-label="缩放控制">
            <button class="zoom-btn" id="zoomOutBtn" type="button">－</button>
            <button class="zoom-btn" id="zoomResetBtn" type="button">100%</button>
            <button class="zoom-btn" id="zoomInBtn" type="button">＋</button>
          </div>
          <div class="zoom-mini time-scale-panel" id="timeScalePanel">
            <div class="zoom-mini-title">时间尺拉伸</div>
            <div class="time-scale-row">
              <button class="zoom-btn time-scale-btn" id="timeScaleShrinkBtn" type="button" aria-label="缩短时间尺">－</button>
              <input class="time-scale-slider" id="timeScaleSlider" type="range" min="1" max="3.5" step="0.25" value="1" aria-label="时间尺拉伸倍率" />
              <button class="zoom-btn time-scale-btn" id="timeScaleExpandBtn" type="button" aria-label="拉长时间尺">＋</button>
            </div>
            <div class="time-scale-meta">
              <span class="time-scale-hint">拉长后可拉开近时间消息</span>
              <strong class="time-scale-value" id="timeScaleLabel">1.0x</strong>
            </div>
          </div>
          <div class="zoom-mini" id="zoomMini">
            <div class="zoom-mini-title">全局缩略图</div>
            <div class="mini-map" id="miniMap">
              <div class="mini-map-viewport" id="miniViewport"></div>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>

  <script id="data" type="application/json">__PAYLOAD__</script>
  <script>__INLINE_JS__</script>
</body>
</html>
