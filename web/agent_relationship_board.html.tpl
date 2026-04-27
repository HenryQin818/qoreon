<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>组织战略 · Qoreon</title>
  <link rel="icon" href="data:," />
  <style>__INLINE_CSS__</style>
</head>
<body>
  <div class="page-shell">
    <section class="board-shell">
      <header class="toolbar">
        <div class="toolbar-main">
          <div class="chip-group" id="platformModeTabs" aria-label="平台视角" hidden>
            <button class="chip is-active" data-platform-layout="project" type="button">项目</button>
            <button class="chip" data-platform-layout="agent" type="button">Agent</button>
          </div>
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
        <div class="toolbar-filters">
          <div class="project-filter-wrap is-hidden" id="platformProjectFilterWrap" hidden>
            <button class="chip" id="platformProjectFilterBtn" type="button">项目筛选</button>
            <div class="project-filter-panel" id="platformProjectFilterPanel" hidden>
              <div class="project-filter-head">
                <div class="project-filter-title">项目筛选</div>
                <div class="project-filter-summary" id="platformProjectFilterSummary">已选 0 / 0</div>
              </div>
              <div class="project-filter-actions">
                <button class="chip mini" id="platformProjectSelectAllBtn" type="button">全选</button>
                <button class="chip mini" id="platformProjectInvertBtn" type="button">反选</button>
                <button class="chip mini" id="platformProjectClearBtn" type="button">清空</button>
              </div>
              <div class="project-filter-list" id="platformProjectFilterList"></div>
              <div class="project-filter-actions submit">
                <button class="chip" id="platformProjectCancelBtn" type="button">取消</button>
                <button class="chip is-active" id="platformProjectApplyBtn" type="button">应用</button>
              </div>
            </div>
          </div>
          <div class="chip-group" id="platformCommScopeFilters" aria-label="沟通范围过滤" hidden>
            <span class="toolbar-label">范围</span>
            <button class="chip is-active" data-comm-scope="all" type="button">全部</button>
            <button class="chip" data-comm-scope="cross" type="button">跨项目</button>
            <button class="chip" data-comm-scope="high" type="button">高频</button>
          </div>
          <div class="chip-group" id="commTypeFilters" aria-label="连线类型过滤">
            <span class="toolbar-label">连线</span>
            <button class="chip is-active" data-comm-kind="user" type="button">用户参与</button>
            <button class="chip is-active" data-comm-kind="agent" type="button">Agent之间</button>
          </div>
          <div class="chip-group" id="platformCommCountFilters" aria-label="沟通数量过滤" hidden>
            <span class="toolbar-label">沟通量</span>
            <button class="chip is-active" data-comm-count-min="0" type="button">全部</button>
            <button class="chip" data-comm-count-min="2" type="button">2+</button>
            <button class="chip" data-comm-count-min="5" type="button">5+</button>
            <button class="chip" data-comm-count-min="10" type="button">10+</button>
          </div>
        </div>
      </header>

      <div class="meta-row">
        <div id="boardMeta">组织战略加载中...</div>
        <div id="summaryMeta">背景板 0 · Agent 0 · 沟通线 0</div>
      </div>

      <div class="status-banner is-loading" id="statusBanner">正在加载组织战略...</div>

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
            <div class="panel-section-title" id="rosterSectionTitle">Agent 节点池</div>
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
          </svg>
          <div class="groups-layer" id="groupsLayer"></div>
          <div class="group-chip-layer" id="groupChipLayer"></div>
          <div class="nodes-layer" id="nodesLayer"></div>
        </div>
        </div>
      </div>

    </section>

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

  </div>

  <div class="bubble-tooltip" id="bubbleTooltip"></div>

  <script id="data" type="application/json">__PAYLOAD__</script>
  <script>__INLINE_JS__</script>
</body>
</html>
