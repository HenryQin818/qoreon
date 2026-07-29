<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Qoreon 开源同步与协作排程</title>
  <link rel="icon" href="data:," />
  <style>__INLINE_CSS__</style>
</head>
<body>
  <div class="page-shell">
    <header class="hero">
      <div class="hero-copy">
        <div class="hero-kicker" id="heroKicker">Open Source Sync Board</div>
        <h1 id="heroTitle">Qoreon 开源同步与协作排程</h1>
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
      <a class="link-chip" id="statusReportLink" href="/share/project-status-report.html">情况汇报</a>
      <a class="link-chip" id="communicationLink" href="/share/project-communication-audit.html">通讯分析</a>
      <a class="link-chip" id="sessionHealthLink" href="/share/project-session-health-dashboard.html">会话健康</a>
    </nav>

    <main class="content">
      <section class="summary-grid" id="summaryGrid"></section>

      <section class="section-block">
        <div class="section-head">
          <div>
            <h2 id="versionBoardTitle">版本差距看板</h2>
            <p id="versionBoardSubtitle">把当前真源、上一轮冻结批次和公开候选放到同一屏上看。</p>
          </div>
        </div>
        <div class="decision-banner" id="versionDecision"></div>
        <div class="version-grid" id="versionGrid"></div>
        <div class="metric-grid" id="metricGrid"></div>
      </section>

      <section class="section-block">
        <div class="section-head">
          <div>
            <h2>大步骤时间轴</h2>
            <p>只看这一条，就知道当前做到哪一步、下一步该盯什么。</p>
          </div>
        </div>
        <div class="timeline-lane" id="majorTimeline"></div>
      </section>

      <section class="section-block">
        <div class="section-head">
          <div>
            <h2>当前两仓快照</h2>
            <p>同一屏展示真源仓和公开仓，避免只剩口头同步关系。</p>
          </div>
        </div>
        <div class="repo-grid" id="repoGrid"></div>
      </section>

      <section class="section-block">
        <div class="section-head">
          <div>
            <h2>固定工作法</h2>
            <p>把多仓维护收敛成 4 层，不再做双向混改。</p>
          </div>
        </div>
        <div class="model-grid" id="modelGrid"></div>
      </section>

      <section class="section-block">
        <div class="section-head">
          <div>
            <h2>今日执行排程</h2>
            <p>按批次接力推进：我先出 export-prep，项目组再桥接、导出、文档、测试、收口。</p>
          </div>
        </div>
        <div class="phase-lane" id="phaseLane"></div>
      </section>

      <section class="section-block">
        <div class="section-head">
          <div>
            <h2>角色分工</h2>
            <p>谁负责哪一段、把结果交给谁，在这里固定下来。</p>
          </div>
        </div>
        <div class="role-grid" id="roleGrid"></div>
      </section>

      <section class="section-block">
        <div class="section-head">
          <div>
            <h2>差异保留规则</h2>
            <p>后续长期存在的差异必须显式归位，不能靠人工记忆。</p>
          </div>
        </div>
        <div class="difference-grid" id="differenceGrid"></div>
      </section>

      <section class="two-col">
        <article class="panel">
          <div class="section-head">
            <div>
              <h2>当前协作链路</h2>
              <p>记录当前已经建立的 run 和等待中的接力点。</p>
            </div>
          </div>
          <div class="stack-list" id="currentLinkList"></div>
        </article>

        <article class="panel">
          <div class="section-head">
            <div>
              <h2>下一步动作</h2>
              <p>今天后续只盯关键动作，不把页面变成流水账。</p>
            </div>
          </div>
          <div class="stack-list" id="nextActionList"></div>
        </article>
      </section>

      <section class="two-col">
        <article class="panel">
          <div class="section-head">
            <div>
              <h2>对齐规则</h2>
              <p>以后判断“这次该怎么同步”，默认按这几条处理。</p>
            </div>
          </div>
          <div class="rule-list" id="alignmentRuleList"></div>
          <div class="rebuild-box">
            <div class="rebuild-label">重建命令</div>
            <code class="rebuild-code" id="rebuildCommand">-</code>
          </div>
        </article>

        <article class="panel">
          <div class="section-head">
            <div>
              <h2>参考资料</h2>
              <p>保留当前同步策略依赖的关键沉淀与主任务。</p>
            </div>
          </div>
          <div class="reference-list" id="referenceList"></div>
        </article>
      </section>
    </main>
  </div>

  <script id="data" type="application/json">__PAYLOAD__</script>
  <script>__INLINE_JS__</script>
</body>
</html>
