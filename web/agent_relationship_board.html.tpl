<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>关系画板 · 小秘书</title>
  <style>__INLINE_CSS__</style>
</head>
<body>
  <div class="page-shell">
    <section class="board-shell">
      <header class="toolbar">
        <div class="toolbar-left">
          <a class="chip link" id="taskLink" href="/share/project-task-dashboard.html">任务页</a>
          <a class="chip link" id="curtainLink" href="/share/project-agent-curtain.html">消息瀑布</a>
          <button class="chip" id="refreshBtn" type="button">刷新</button>
          <button class="chip" id="saveLayoutBtn" type="button">保存布局</button>
          <button class="chip" id="exportConfigBtn" type="button">导出JSON</button>
          <button class="chip" id="copyConfigBtn" type="button">复制配置</button>
          <span class="chip readonly">正式页 P2</span>
          <span class="chip env" id="envBadge">stable</span>
        </div>
        <div class="toolbar-center">
          <div class="chip-group" id="timeTabs" aria-label="时间窗口">
            <button class="chip is-active" data-window="1h" type="button">1小时</button>
            <button class="chip" data-window="3h" type="button">3小时</button>
            <button class="chip" data-window="24h" type="button">24小时</button>
            <button class="chip" data-window="custom" type="button">自定义</button>
          </div>
          <div class="custom-range" id="customRange" hidden>
            <input class="time-input" id="customStartInput" type="datetime-local" />
            <span class="custom-sep">至</span>
            <input class="time-input" id="customEndInput" type="datetime-local" />
            <button class="chip" id="customApplyBtn" type="button">应用</button>
          </div>
        </div>
        <div class="toolbar-right">
          <div class="toolbar-stack">
            <div class="chip-group compact" aria-label="建线类型">
              <span class="toolbar-label">建线</span>
              <button class="chip is-active" data-relation-type="business" type="button">主责</button>
              <button class="chip" data-relation-type="support" type="button">支撑</button>
              <button class="chip" data-relation-type="dependency" type="button">依赖</button>
            </div>
            <div class="chip-group compact" aria-label="图例显示">
              <span class="toolbar-label">图例</span>
              <button class="chip is-active" data-visibility="business" type="button">主责</button>
              <button class="chip is-active" data-visibility="support" type="button">支撑</button>
              <button class="chip is-active" data-visibility="dependency" type="button">依赖</button>
              <button class="chip is-active" data-visibility="message" type="button">通讯</button>
              <button class="chip is-active" data-visibility="labels" type="button">标签</button>
            </div>
          </div>
          <button class="chip" id="toggleLayersBtn" type="button">背景板</button>
          <button class="chip" id="toggleDetailBtn" type="button">详情</button>
        </div>
      </header>

      <div class="meta-row">
        <div id="boardMeta">关系画板加载中...</div>
        <div id="summaryMeta">背景板 0 · Agent 0 · 消息 0 · 通讯 0</div>
      </div>

      <div class="status-banner is-loading" id="statusBanner">正在加载关系画板...</div>

      <aside class="floating-panel layers-panel collapsed" id="layersPanel">
        <div class="panel-head">
          <div>
            <div class="panel-kicker">背景板图层</div>
            <div class="panel-title">图层与节点</div>
          </div>
          <button class="panel-close" id="closeLayersBtn" type="button">关闭</button>
        </div>
        <div class="panel-body">
          <div class="panel-section">
            <div class="panel-section-title">背景板图层（可拖动排序）</div>
            <div id="groupList"></div>
          </div>
          <div class="panel-section">
            <div class="panel-section-title">Agent 节点池</div>
            <input class="field-input compact" id="searchInput" placeholder="搜索 Agent / 通道 / 角色" />
            <div id="rosterList"></div>
          </div>
        </div>
      </aside>
      <button class="edge-handle left" id="openLayersBtn" type="button">背景板</button>

      <aside class="floating-panel detail-panel collapsed" id="detailPanel">
        <div class="panel-head">
          <div>
            <div class="panel-kicker">对象详情</div>
            <div class="panel-title" id="detailTitle">未选中</div>
          </div>
          <button class="panel-close" id="closeDetailBtn" type="button">关闭</button>
        </div>
        <div class="panel-body" id="detailBody"></div>
      </aside>
      <button class="edge-handle right" id="openDetailBtn" type="button">详情</button>

      <div class="stage-wrap" id="stageWrap" hidden>
        <div class="stage-viewport" id="stageViewport">
        <div class="stage" id="stage">
          <div class="row-label row-master">总管</div>
          <div class="row-label row-assist">营运（辅助）</div>
          <div class="row-label row-dev">开发（子级）</div>
          <div class="row-label row-other">新业务（其他）</div>
          <svg class="lines-layer" id="linesSvg" aria-hidden="true">
            <defs>
              <marker id="relationArrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto" markerUnits="strokeWidth">
                <path d="M0,0 L10,5 L0,10 z" fill="rgba(238,245,255,0.86)"></path>
              </marker>
            </defs>
          </svg>
          <div class="groups-layer" id="groupsLayer"></div>
          <div class="group-chip-layer" id="groupChipLayer"></div>
          <div class="nodes-layer" id="nodesLayer"></div>
        </div>
        </div>
      </div>

      <div class="floating-replay" id="replayBar">
        <span class="replay-label">回放</span>
        <button class="chip" id="playBtn" type="button">播放</button>
        <button class="chip" id="pauseBtn" type="button">暂停</button>
        <button class="chip" id="replayResetBtn" type="button">重播</button>
        <button class="chip is-active" data-replay-speed="1" type="button">1x</button>
        <button class="chip" data-replay-speed="4" type="button">4x</button>
        <button class="chip" data-replay-speed="10" type="button">10x</button>
        <div class="replay-timeline">
          <span class="replay-time" id="replayCurrentTime">静止视图</span>
          <div class="replay-track">
            <div class="replay-markers" id="replayMarkers"></div>
            <input class="replay-slider" id="replaySlider" type="range" min="0" max="1000" value="1000" />
          </div>
          <span class="replay-time" id="replayEndTime">--</span>
        </div>
      </div>

      <div class="floating-mini-map" id="miniMapBox">
        <div class="mini-map-toolbar">
          <div class="panel-kicker">缩略图</div>
          <div class="mini-map-actions">
            <button class="chip mini" id="zoomOutBtn" type="button">－</button>
            <button class="chip mini" id="zoomResetBtn" type="button">100%</button>
            <button class="chip mini" id="zoomInBtn" type="button">＋</button>
          </div>
        </div>
        <div class="mini-map" id="miniMap"></div>
      </div>
    </section>
  </div>

  <div class="bubble-tooltip" id="bubbleTooltip"></div>

  <div class="dialog-mask" id="messageDialog" hidden>
    <div class="dialog-card">
      <div class="dialog-head">
        <div>
          <div class="dialog-kicker">消息详情</div>
          <div class="dialog-title" id="messageDialogTitle">-</div>
        </div>
        <button class="panel-close" id="messageDialogCloseBtn" type="button">关闭</button>
      </div>
      <div class="dialog-body" id="messageDialogBody"></div>
    </div>
  </div>

  <script id="data" type="application/json">__PAYLOAD__</script>
  <script>__INLINE_JS__</script>
</body>
</html>
