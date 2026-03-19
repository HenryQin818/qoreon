<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>项目情况汇报 · 小秘书</title>
  <style>__INLINE_CSS__</style>
</head>
<body>
  <div class="page-shell">
    <header class="hero">
      <div class="hero-copy">
        <div class="hero-kicker" id="heroKicker">Project Status Brief</div>
        <h1 id="heroTitle">项目情况汇报</h1>
        <p class="hero-sub" id="heroSubtitle">-</p>
      </div>
      <div class="hero-meta">
        <span class="hero-chip hero-chip-strong" id="generatedAtChip">生成中</span>
        <span class="hero-chip" id="sourceFileChip">数据源 -</span>
      </div>
    </header>

    <nav class="quick-links" aria-label="快捷入口">
      <a class="link-chip" id="overviewLink" href="/share/project-overview-dashboard.html">项目总览</a>
      <a class="link-chip" id="taskLink" href="/share/project-task-dashboard.html">任务页</a>
      <a class="link-chip" id="communicationLink" href="/share/project-communication-audit.html">通讯分析</a>
      <a class="link-chip" id="sessionHealthLink" href="/share/project-session-health-dashboard.html">会话健康</a>
    </nav>

    <main class="content">
      <section class="summary-grid" id="summaryGrid"></section>

      <section class="two-col">
        <article class="panel">
          <div class="section-head">
            <div>
              <h2>仓库快照</h2>
              <p>构建时自动读取当前仓库状态，避免页面只剩口头结论。</p>
            </div>
          </div>
          <div class="kv-grid" id="repoSnapshot"></div>
        </article>

        <article class="panel">
          <div class="section-head">
            <div>
              <h2>更新规则</h2>
              <p>以后更新进展时，优先只改数据源，不先改页面骨架。</p>
            </div>
          </div>
          <div class="rule-list" id="updateRules"></div>
          <div class="rebuild-box">
            <div class="rebuild-label">重建命令</div>
            <code class="rebuild-code" id="rebuildCommand">-</code>
          </div>
        </article>
      </section>

      <section class="section-block">
        <div class="section-head">
          <div>
            <h2>环境与仓库矩阵</h2>
            <p>把当前有效环境与历史退役位放到同一屏，避免继续沿用过时口径。</p>
          </div>
        </div>
        <div class="env-grid" id="environmentGrid"></div>
      </section>

      <section class="section-block">
        <div class="section-head">
          <div>
            <h2>当前工作流</h2>
            <p>聚焦正在推进的工作块，而不是把所有历史平铺。</p>
          </div>
        </div>
        <div class="workstream-grid" id="workstreamGrid"></div>
      </section>

      <section class="section-block split-block">
        <article class="panel">
          <div class="section-head">
            <div>
              <h2>关键风险</h2>
              <p>只保留当前最影响推进的风险项。</p>
            </div>
          </div>
          <div class="stack-list" id="riskList"></div>
        </article>
        <article class="panel">
          <div class="section-head">
            <div>
              <h2>下一步动作</h2>
              <p>下一轮要做什么、谁来推进，在这里一眼看清。</p>
            </div>
          </div>
          <div class="stack-list" id="nextActionList"></div>
        </article>
      </section>

      <section class="section-block timeline-section">
        <div class="section-head">
          <div>
            <h2>里程碑与最近更新</h2>
            <p>左边看历史切换节点，右边看最近结论，适合持续汇报。</p>
          </div>
        </div>
        <div class="timeline-grid">
          <article class="panel">
            <div class="timeline-list" id="milestoneList"></div>
          </article>
          <article class="panel">
            <div class="timeline-list" id="updateList"></div>
          </article>
        </div>
      </section>

      <section class="section-block">
        <div class="section-head">
          <div>
            <h2>参考资料</h2>
            <p>保留当前判断依赖的关键制度与方案文件，方便回看。</p>
          </div>
        </div>
        <div class="reference-list" id="referenceList"></div>
      </section>
    </main>
  </div>

  <script id="data" type="application/json">__PAYLOAD__</script>
  <script>__INLINE_JS__</script>
</body>
</html>
