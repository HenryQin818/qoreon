<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>生产性能压力诊断看板 · Qoreon</title>
  <style>__INLINE_CSS__</style>
</head>
<body>
  <div class="page-shell">
    <header class="hero">
      <div class="hero-copy">
        <div class="hero-kicker" id="heroKicker">Ops Pressure Board</div>
        <h1 id="heroTitle">生产性能压力诊断看板</h1>
        <p class="hero-sub" id="heroSubtitle">读取中</p>
        <div class="hero-meta">
          <span class="hero-chip hero-chip-strong" id="generatedAtChip">生成中</span>
          <span class="hero-chip" id="severityChip">严重度 -</span>
          <span class="hero-chip" id="runtimeChip">runtime -</span>
        </div>
      </div>

      <section class="hero-summary-card" id="heroSummaryCard" aria-label="综合性能结论">
        <div class="hero-summary-head">
          <div>
            <div class="hero-summary-kicker">综合结论</div>
            <div class="hero-summary-title" id="heroSummaryTitle">正在汇总</div>
          </div>
          <span class="hero-summary-badge" id="severityBadge">-</span>
        </div>
        <div class="hero-summary-body">
          <div class="gauge-ring gauge-ring-hero" id="overallGauge">
            <div class="gauge-core">
              <div class="gauge-value" id="overallScore">--</div>
              <div class="gauge-label">压力指数</div>
            </div>
          </div>
          <div class="hero-summary-texts">
            <p class="hero-summary-text" id="heroSummaryText">正在读取当前压力结论。</p>
            <div class="hero-mini-signals" id="heroSignalGrid"></div>
          </div>
        </div>
      </section>
    </header>

    <section class="headline-band" id="statusBanner"></section>

    <main class="content">
      <section class="section-block command-center">
        <div class="section-head compact-head">
          <div>
            <h2>首屏总览</h2>
            <p>把核心指标、四层压力、综合雷达和时间窗尽量压进第一屏，先看结论，再看细节。</p>
          </div>
        </div>
        <div class="command-grid">
          <div class="command-primary">
            <div class="signal-grid" id="signalGrid"></div>
            <div class="panel-grid compact-panel-grid" id="panelGrid"></div>
          </div>
          <div class="command-side">
            <div class="radar-card">
              <svg class="radar-svg" id="radarChart" viewBox="0 0 360 360" aria-label="综合压力雷达图"></svg>
            </div>
            <div class="radar-legend compact-legend" id="radarLegend"></div>
          </div>
          <div class="window-chart compact-window-chart" id="windowChart"></div>
        </div>
      </section>

      <section class="section-block intelligence-board">
        <div class="section-head compact-head">
          <div>
            <h2>热点与动作</h2>
            <p>把热点流量、资源占用和处理建议集中在第二层，避免页面越往下越分散。</p>
          </div>
        </div>
        <div class="split-block">
        <article class="panel">
          <div class="section-head">
            <div>
              <h2>热点接口</h2>
              <p>默认看最近 15 分钟的高频接口，优先识别轮询热区。</p>
            </div>
          </div>
          <div class="bar-list" id="endpointList"></div>
        </article>
        <article class="panel">
          <div class="section-head">
            <div>
              <h2>热点项目 / 会话</h2>
              <p>哪些项目和会话正在持续向 stable 打流量，放到同一块看。</p>
            </div>
          </div>
          <div class="bar-list" id="projectList"></div>
          <div class="subsection-divider"></div>
          <div class="bar-list" id="sessionList"></div>
        </article>
        <article class="panel">
          <div class="section-head">
            <div>
              <h2>高占用进程</h2>
              <p>CPU 前排进程以图形卡片展示，快速判断是不是 Chrome、stable 或系统渲染链在顶。</p>
            </div>
          </div>
          <div class="process-grid" id="processList"></div>
        </article>
        <article class="panel">
          <div class="section-head">
            <div>
              <h2>自动化残留</h2>
              <p>单独看 Playwright / chrome-devtools-mcp / automation Chrome，避免和主浏览器混淆。</p>
            </div>
          </div>
          <div class="process-grid" id="automationList"></div>
        </article>
        <article class="panel">
          <div class="section-head">
            <div>
              <h2>建议动作</h2>
              <p>不是把原始数字丢给人，而是给出当前最值得先做的动作顺序。</p>
            </div>
          </div>
          <div class="action-timeline" id="actionList"></div>
        </article>
        <article class="panel">
          <div class="section-head">
            <div>
              <h2>参考真源</h2>
              <p>列出本次诊断依赖的日志和采样入口，方便后续回看。</p>
            </div>
          </div>
          <div class="reference-list" id="referenceList"></div>
        </article>
        </div>
      </section>

      <section class="section-block snapshot-board" id="snapshotDiagnosticsSection">
        <div class="section-head compact-head">
          <div>
            <h2>Sessions Snapshot 诊断</h2>
            <p>只解释 `/api/sessions` 当前的 delivery mode、5s/10s 节奏、失效聚合窗口和最近一次失效/刷新事件，不展开 raw log。</p>
          </div>
        </div>
        <div class="split-block snapshot-split-block">
          <article class="panel">
            <div class="section-head">
              <div>
                <h2>当前快照与功能日志状态</h2>
                <p>把 cadence、TTL、构建来源、最终交付模式与后台摘要压成结构化卡片，先看 stale-first 是否按预期工作。</p>
              </div>
            </div>
            <div class="snapshot-diagnostic-grid" id="snapshotDiagnosticGrid"></div>
            <div class="subsection-divider"></div>
            <div class="snapshot-diagnostic-meta" id="snapshotDiagnosticMeta"></div>
          </article>
          <article class="panel">
            <div class="section-head">
              <div>
                <h2>最近事件与窗口聚合</h2>
                <p>只显示最近 20 条结构化 snapshot 事件，重点解释 invalidation 聚合次数、窗口时长和 delivery mode，不展示 trace 明细。</p>
              </div>
            </div>
            <div class="snapshot-event-list" id="snapshotEventList"></div>
          </article>
        </div>
      </section>
    </main>
  </div>

  <script id="data" type="application/json">__PAYLOAD__</script>
  <script>__INLINE_JS__</script>
</body>
</html>
