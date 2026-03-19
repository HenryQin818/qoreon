<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>通讯分析 · 小秘书</title>
  <style>__INLINE_CSS__</style>
</head>
<body>
  <div class="page-shell">
    <header class="hero">
      <div class="hero-copy">
        <div class="hero-kicker">Communication Audit</div>
        <h1>通讯分析</h1>
        <p class="hero-sub">只读分析发送主体、回复习惯与回执闭环，不触发任何写操作或执行动作。</p>
      </div>
      <div class="hero-actions">
        <span class="badge badge-readonly">只读</span>
        <span class="badge" id="envBadge">环境 -</span>
        <button class="btn btn-ghost" id="refreshBtn" type="button">刷新</button>
        <button class="btn btn-primary" id="deepScanBtn" type="button">深扫运行态</button>
      </div>
    </header>

    <nav class="quick-links" aria-label="快捷入口">
      <a class="link-chip" id="overviewLink" href="/share/project-overview-dashboard.html">返回总揽</a>
      <a class="link-chip" id="taskLink" href="/share/project-task-dashboard.html">打开任务页</a>
      <a class="link-chip" id="statusReportLink" href="/share/project-status-report.html">情况汇报</a>
      <a class="link-chip" id="sessionHealthLink" href="/share/project-session-health-dashboard.html">会话健康</a>
    </nav>

    <section class="guard-panel">
      <div class="guard-title">安全边界</div>
      <div class="guard-grid">
        <div class="guard-item">默认只扫 `hot + .runs`，避免拖慢主业务。</div>
        <div class="guard-item">结果走服务端缓存，不做实时重算轰炸。</div>
        <div class="guard-item">分析页与任务执行页分离，按需打开。</div>
      </div>
      <div class="guard-meta" id="guardMeta">加载中...</div>
    </section>

    <main class="content">
      <section class="overview-cards" id="overviewCards"></section>
      <section class="visual-grid" id="visualGrid"></section>
      <section class="report-switcher">
        <div class="section-head">
          <div>
            <h2>分析范围</h2>
            <p>默认对比当前协作面与仓库根历史样本；深扫后会追加运行态全量。</p>
          </div>
          <div class="tabs" id="scopeTabs"></div>
        </div>
        <div class="report-grid">
          <section class="panel panel-main">
            <div class="panel-head">
              <div>
                <h3 id="reportTitle">通讯概览</h3>
                <p id="reportDesc">-</p>
              </div>
              <div class="panel-meta" id="reportMeta">-</div>
            </div>
            <div class="metric-grid" id="metricGrid"></div>
          </section>
          <section class="panel panel-side">
            <div class="panel-head">
              <div>
                <h3>响应判断</h3>
                <p>基于时间窗的同通道/同会话相关性估算。</p>
              </div>
            </div>
            <div class="response-list" id="responseList"></div>
          </section>
        </div>
      </section>

      <section class="section-block">
        <div class="section-head">
          <div>
            <h2>结构化分布</h2>
            <p>看当前沟通方式是否真的按制度落盘。</p>
          </div>
        </div>
        <div class="table-grid" id="distributionGrid"></div>
      </section>

      <section class="section-block">
        <div class="section-head">
          <div>
            <h2>热点对象</h2>
            <p>识别主要沟通通道、发送者与降级原因。</p>
          </div>
        </div>
        <div class="table-grid" id="rankingGrid"></div>
      </section>
    </main>
  </div>

  <script id="data" type="application/json">__PAYLOAD__</script>
  <script>__INLINE_JS__</script>
</body>
</html>
