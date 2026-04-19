<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Qoreon 平台业务架构画板</title>
  <link rel="icon" href="data:," />
  <style>__INLINE_CSS__</style>
</head>
<body>
  <div class="page-shell">
    <header class="hero">
      <div class="hero-copy">
        <div class="hero-kicker" id="heroKicker">Platform Vision Board</div>
        <h1 id="heroTitle">Qoreon 平台业务架构画板</h1>
        <p class="hero-sub" id="heroSubtitle">-</p>
      </div>
      <div class="hero-meta">
        <span class="hero-chip hero-chip-strong" id="deliveryStateChip">目标态</span>
        <span class="hero-chip" id="generatedAtChip">生成中</span>
        <span class="hero-chip" id="sourceFileChip">数据源 -</span>
      </div>
    </header>

    <nav class="quick-links" aria-label="快捷入口">
      <a class="link-chip" id="overviewLink" href="/share/project-overview-dashboard.html">项目总览</a>
      <a class="link-chip" id="taskLink" href="/share/project-task-dashboard.html">任务页</a>
      <a class="link-chip" id="statusReportLink" href="/share/project-status-report.html">情况汇报</a>
      <a class="link-chip" id="openSourceSyncLink" href="/share/project-open-source-sync-board.html">开源同步</a>
      <a class="link-chip" id="communicationLink" href="/share/project-communication-audit.html">通讯分析</a>
      <a class="link-chip" id="sessionHealthLink" href="/share/project-session-health-dashboard.html">会话健康</a>
    </nav>

    <main class="content">
      <section class="summary-grid" id="summaryGrid"></section>

      <section class="two-col">
        <article class="panel">
          <div class="section-head">
            <div>
              <h2>平台定位</h2>
              <p>这张图描述的是理想中的平台角色，而不是某一轮代码目录结构。</p>
            </div>
          </div>
          <div class="positioning-text" id="positioningText">-</div>
        </article>

        <article class="panel">
          <div class="section-head">
            <div>
              <h2>冻结口径</h2>
              <p>后续对内对外讲平台时，先守住这个区分。</p>
            </div>
          </div>
          <div class="freeze-note" id="freezeNoteText">-</div>
        </article>
      </section>

      <section class="two-col">
        <article class="panel">
          <div class="section-head">
            <div>
              <h2>业务目标</h2>
              <p>先看平台要解决什么问题，再理解它为什么要作为中间层存在。</p>
            </div>
          </div>
          <div class="goal-list" id="goalPointList"></div>
        </article>

        <article class="panel">
          <div class="section-head">
            <div>
              <h2>范围与边界</h2>
              <p>范围内、范围外和反定义分开写，后续表达才不会再次混掉。</p>
            </div>
          </div>
          <div class="scope-grid" id="scopeGrid"></div>
        </article>
      </section>

      <section class="section-block">
        <div class="section-head">
          <div>
            <h2>抽屉式层级结构</h2>
            <p>从上游协作者到平台中台，再到底层业务与系统，重点看清“谁接入、谁收敛、谁执行”。</p>
          </div>
        </div>
        <div class="drawer-stage">
          <div class="drawer-stack" id="drawerStack"></div>
          <aside class="rail-panel">
            <div class="section-head rail-head">
              <div>
                <h3>跨层治理轨</h3>
                <p>这些能力不属于单一抽屉，而是贯穿整个平台。</p>
              </div>
            </div>
            <div class="rail-grid" id="railGrid"></div>
          </aside>
        </div>
      </section>

      <section class="section-block">
        <div class="section-head">
          <div>
            <h2>平台流转路径</h2>
            <p>核心闭环只有四步：接入、收敛、执行、回流，不把系统变成散乱聊天记录。</p>
          </div>
        </div>
        <div class="flow-lane" id="flowLane"></div>
      </section>

      <section class="two-col">
        <article class="panel">
          <div class="section-head">
            <div>
              <h2>平台要支撑的业务形态</h2>
              <p>平台不是只服务研发，而是承接整个项目运行过程。</p>
            </div>
          </div>
          <div class="card-grid" id="scenarioGrid"></div>
        </article>

        <article class="panel">
          <div class="section-head">
            <div>
              <h2>边界与反定义</h2>
              <p>先讲清它不是什么，后面才不容易跑偏成任务工具或 AI 壳子。</p>
            </div>
          </div>
          <div class="card-grid" id="boundaryGrid"></div>
        </article>
      </section>

      <section class="two-col">
        <article class="panel">
          <div class="section-head">
            <div>
              <h2>推进节奏</h2>
              <p>把当前阶段、关键里程碑和唯一主动作摆在同一屏里，便于评审收口。</p>
            </div>
          </div>
          <div class="tracker-meta" id="trackerMeta"></div>
          <div class="milestone-lane" id="milestoneLane"></div>
          <div class="tracker-note-grid">
            <article class="tracker-note-card">
              <div class="tracker-note-label">当前结论</div>
              <p class="tracker-note-text" id="trackerConclusion">-</p>
            </article>
            <article class="tracker-note-card">
              <div class="tracker-note-label">下一步动作</div>
              <p class="tracker-note-text" id="trackerNextAction">-</p>
            </article>
          </div>
        </article>

        <article class="panel">
          <div class="section-head">
            <div>
              <h2>30 秒口播</h2>
              <p>适合讲给产品、协作者或评审方听，不需要再临时重写表达口径。</p>
            </div>
          </div>
          <div class="talk-track" id="talkTrackList"></div>
        </article>
      </section>

      <section class="two-col">
        <article class="panel">
          <div class="section-head">
            <div>
              <h2>统一口径</h2>
              <p>以后讨论平台结构、拆层和评审时，默认先按这几条来。</p>
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
              <p>本页是目标态画板；要对照现状，请结合这些真源一起看。</p>
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
