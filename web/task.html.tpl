<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>项目任务看板 · Qoreon</title>
  <style>__INLINE_CSS__</style>
  <script>
    (() => {
      try {
        const rawHash = String(window.location.hash || "").replace(/^#/, "").trim();
        if (!rawHash) return;
        if (!/(?:^|&)(?:tm|mode)=schedule(?:&|$)/.test(rawHash)) return;
        const params = new URLSearchParams(rawHash);
        params.delete("tm");
        params.delete("mode");
        params.set("pm", "t");
        const nextHash = params.toString();
        history.replaceState(null, "", nextHash ? ("#" + nextHash) : (window.location.pathname + window.location.search));
      } catch (_) {}
    })();
  </script>
</head>
<body>
  <div class="ambient-bg">
    <div class="blob blob-1"></div>
    <div class="blob blob-2"></div>
    <div class="blob blob-3"></div>
    <div class="blob blob-4"></div>
    <div class="blob blob-5"></div>
    <div class="blob blob-6"></div>
    <div class="blob blob-7"></div>
    <div class="blob blob-8"></div>
  </div>

  <div class="shell">
    <!-- Header -->
    <header>
      <div class="header-main">
        <a class="back-link" id="backToOverview" href="#" title="返回项目总览">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" width="18" height="18">
            <path d="M15 19l-7-7 7-7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span>总览</span>
        </a>
        <div class="project-info">
          <h1 class="project-title" id="projectTitle">项目名称</h1>
          <div class="project-meta-row">
            <span class="project-desc" id="projectDesc"></span>
            <span class="env-chip" id="envBadge" hidden></span>
          </div>
        </div>
      </div>
      <div class="header-nav" id="headerNav">
        <div class="header-mode-tabs" role="tablist" aria-label="一级页面切换">
          <button class="header-mode-btn" id="headerPanelConvBtn" data-panel-mode="conv" role="tab" aria-selected="false">对话</button>
          <button class="header-mode-btn" id="headerPanelTaskBtn" data-panel-mode="task" role="tab" aria-selected="false">任务</button>
          <button class="header-mode-btn active" id="headerPanelChannelBtn" data-panel-mode="channel" role="tab" aria-selected="true">知识</button>
          <button class="header-mode-btn is-disabled" id="headerPanelArchPreviewBtn" type="button" role="tab" aria-selected="false" aria-disabled="true" disabled title="架构板块敬请期待">
            <span>架构</span>
            <span class="header-mode-soon">敬请期待</span>
          </button>
        </div>
      </div>
      <div class="hctrl">
        <!-- 移动端通道选择器 -->
        <div class="channel-selector" id="channelSelector">
          <button class="channel-selector-btn" id="channelSelectorBtn">
            <span class="channel-name" id="channelName">选择通道</span>
            <svg viewBox="0 0 24 24" fill="none" width="14" height="14">
              <path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
          <div class="channel-dropdown" id="channelDropdown">
            <div class="channel-list" id="channelList"></div>
          </div>
        </div>
        <div class="system-settings" id="systemSettingsWrap">
          <button class="system-settings-trigger" id="systemSettingsTrigger" type="button" aria-haspopup="true" aria-expanded="false" title="打开系统设置">
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M4 7h16M7 12h10M10 17h4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
            </svg>
            <span>系统设置</span>
            <span class="system-settings-count">7项</span>
          </button>
          <div class="system-settings-popover" id="systemSettingsPopover" role="menu" aria-label="系统设置">
            <button class="system-settings-item project-config-btn" id="projectConfigBtn" type="button" title="打开 项目配置">
              <div class="system-settings-item-main">
                <span class="system-settings-item-title">项目配置</span>
                <span class="system-settings-item-desc">环境、工作树、规则、运行参数</span>
              </div>
              <span class="system-settings-badge">配置</span>
            </button>
            <button class="system-settings-item project-config-btn" id="shareProjectBtn" type="button" title="打开 分享项目">
              <div class="system-settings-item-main">
                <span class="system-settings-item-title">分享项目</span>
                <span class="system-settings-item-desc">授权 Agent、生成当前页受限分享链接</span>
              </div>
              <span class="system-settings-badge">分享</span>
            </button>
            <button class="system-settings-item" id="projectAgentDirectoryBtn" type="button" title="打开项目通讯录">
              <div class="system-settings-item-main">
                <span class="system-settings-item-title">通讯录</span>
                <span class="system-settings-item-desc">项目 Agent 名录、角色、主子会话</span>
              </div>
              <span class="system-settings-badge">Agent</span>
            </button>
            <button class="system-settings-item" id="projectAgentCurtainBtn" type="button" title="打开 消息瀑布">
              <div class="system-settings-item-main">
                <span class="system-settings-item-title">消息瀑布</span>
                <span class="system-settings-item-desc">跨通道消息流与处理轨迹</span>
              </div>
              <span class="system-settings-badge">时间线</span>
            </button>
            <button class="system-settings-item" id="projectRelationshipBoardBtn" type="button" title="打开 组织战略">
              <div class="system-settings-item-main">
                <div class="system-settings-item-heading">
                  <span class="system-settings-item-title">组织战略</span>
                  <span class="system-settings-item-new">NEW</span>
                </div>
                <span class="system-settings-item-desc">项目内组织结构与协作关系</span>
              </div>
              <span class="system-settings-badge">组织</span>
            </button>
            <button class="system-settings-item" id="sessionHealthBtn" type="button" title="打开 会话健康看板">
              <div class="system-settings-item-main">
                <span class="system-settings-item-title">会话健康</span>
                <span class="system-settings-item-desc">会话连通、CLI 状态、异常提醒</span>
              </div>
              <span class="system-settings-badge">监控</span>
            </button>
            <button class="system-settings-item project-root-reveal-btn" id="projectRootRevealBtn" type="button" title="打开项目文件夹">
              <div class="system-settings-item-main">
                <span class="system-settings-item-title">打开项目文件夹</span>
                <span class="system-settings-item-desc">定位当前项目真实目录</span>
              </div>
              <span class="system-settings-badge">Finder</span>
            </button>
          </div>
        </div>
        <div class="legacy-header-tools" hidden aria-hidden="true">
          <button class="icon-text-btn project-auto-header-btn" id="projectAutoHeaderBtn" title="项目调度与提醒" style="display:none;">
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M12 3v4m0 10v4M3 12h4m10 0h4M5.64 5.64l2.83 2.83m7.06 7.06 2.83 2.83m0-12.72-2.83 2.83m-7.06 7.06-2.83 2.83" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
              <circle cx="12" cy="12" r="3.5" stroke="currentColor" stroke-width="1.8"/>
            </svg>
            <span>项目调度</span>
          </button>
          <input class="input" id="q" placeholder="搜索..." hidden />
        </div>
      </div>
    </header>

    <!-- 移动端模式切换栏 -->
    <div class="mobile-mode-bar" id="mobileModeBar">
      <div class="pmseg" role="tablist" aria-label="移动端模式切换">
        <button class="segbtn" id="panelConvBtnMobile" data-panel-mode="conv" role="tab">对话</button>
        <button class="segbtn" id="panelTaskBtnMobile" data-panel-mode="task" role="tab">任务</button>
        <button class="segbtn active" id="panelChannelBtnMobile" data-panel-mode="channel" role="tab">知识</button>
        <button class="segbtn segbtn-disabled" id="panelArchPreviewBtnMobile" type="button" role="tab" aria-disabled="true" disabled title="架构板块敬请期待">
          <span>架构</span>
          <span class="segbtn-note">敬请期待</span>
        </button>
      </div>
    </div>

    <!-- 项目级自动调度/提醒状态展示（12-2） -->
    <div class="project-auto-mask" id="projectAutoWrap" role="dialog" aria-modal="true" aria-label="项目调度与提醒设置">
      <div class="project-auto-dialog" role="document">
        <div class="project-auto-dialog-head">
          <div class="project-auto-dialog-titlewrap">
            <div class="project-auto-dialog-title">项目调度与提醒</div>
            <div class="project-auto-dialog-sub">自动调度、例行提醒状态与提醒记录</div>
          </div>
          <button class="btn" id="projectAutoCloseBtn" type="button" title="关闭">关闭</button>
        </div>
        <div class="project-auto-panel" id="projectAutoPanel"></div>
      </div>
    </div>
    <div class="project-auto-record-drawer-mask" id="projectAutoRecordDrawerMask" role="dialog" aria-modal="true" aria-label="巡查记录抽屉">
      <aside class="project-auto-record-drawer" role="document">
        <div class="project-auto-record-drawer-head">
          <div>
            <div class="project-auto-record-drawer-title">巡查记录</div>
            <div class="project-auto-record-drawer-sub" id="projectAutoRecordDrawerSub">当前暂无巡查记录</div>
          </div>
          <button class="btn" id="projectAutoRecordDrawerCloseBtn" type="button">关闭</button>
        </div>
        <div class="project-auto-record-drawer-list" id="projectAutoRecordDrawerList"></div>
      </aside>
    </div>

    <div class="body">
      <!-- 左侧：通道列表（PC端显示） -->
      <aside id="channelAside">
        <div class="aside-scroll">
          <div class="asideh">
            <div class="asideleft">
              <div class="pmseg" role="tablist" aria-label="页面维度切换" hidden aria-hidden="true">
                <button class="segbtn" id="panelConvBtn" data-panel-mode="conv" role="tab">对话</button>
                <button class="segbtn" id="panelTaskBtn" data-panel-mode="task" role="tab">任务</button>
                <button class="segbtn active" id="panelChannelBtn" data-panel-mode="channel" role="tab">知识</button>
                <button class="segbtn" id="panelOrgBtn" data-panel-mode="org" role="tab">组织</button>
                <button class="segbtn" id="panelArchBtn" data-panel-mode="arch" role="tab">架构</button>
              </div>
              <h2 class="at" id="asideTitle">知识</h2>
              <div class="conv-layout-bar" id="convLayoutBar">
                <div class="conv-layout-tabs" id="convLayoutTabs" role="tablist" aria-label="对话列表展示模式">
                  <button class="conv-layout-tab active" id="convLayoutFlatBtn" type="button" data-conv-layout="flat" role="tab" aria-selected="true">对话</button>
                  <button class="conv-layout-tab" id="convLayoutChannelBtn" type="button" data-conv-layout="channel" role="tab" aria-selected="false">通道块</button>
                </div>
                <div class="aside-actions">
                  <button class="btn aside-text-btn" id="newChannelAsideBtn" type="button" title="新增通道">+通道</button>
                </div>
              </div>
            </div>
            <div class="am" id="asideMeta"></div>
          </div>
          <div class="list" id="leftList"></div>
        </div>
      </aside>
      <div class="conv-resize-handle" id="convResizeHandle" role="separator" aria-orientation="vertical" aria-label="调整对话列表宽度"></div>

      <!-- 中间：列表区（任务列表/对话列表） -->
      <main class="list-view" id="listView">
        <div class="list-header">
          <div class="channel-info" id="channelInfo">
            <div class="channel-info-top">
              <div class="channel-mainline">
                <span class="channel-label" id="channelInfoLabel">当前通道：</span>
                <span class="channel-value" id="currentChannelName">-</span>
              </div>
              <div class="org-mode-top-tabs pmseg" id="orgModeTopTabs" role="tablist" aria-label="架构视图模式切换" hidden aria-hidden="true">
                <button class="segbtn" data-panel-mode="conv" role="tab">对话</button>
                <button class="segbtn" data-panel-mode="task" role="tab">任务</button>
                <button class="segbtn" data-panel-mode="channel" role="tab">知识</button>
                <button class="segbtn" data-panel-mode="org" role="tab">组织</button>
                <button class="segbtn" data-panel-mode="arch" role="tab">架构</button>
              </div>
              <div class="channel-info-actions">
                <button class="btn" id="channelPathCopyBtn" type="button" title="复制通道目录路径">复制路径</button>
                <button class="btn" id="channelPathRevealBtn" type="button" title="在 Finder 中打开通道文件夹">打开通道文件夹</button>
              </div>
            </div>
            <div class="channel-subline" id="channelInfoSub">请选择通道查看详情。</div>
            <div class="chips channel-stats" id="channelInfoStats"></div>
            <div class="channel-path-row" id="channelPathRow">
              <div class="channel-path-text" id="channelPathText" title="点击复制路径">-</div>
            </div>
          </div>
          <div class="filterbar" id="filterBar"></div>
        </div>
        <div class="task-materials-header" id="taskMaterialsHeader">
          <span class="task-materials-title">文件资料</span>
        </div>
        <div class="filelist" id="fileList"></div>
        <!-- 通道知识沉淀区块 -->
        <div class="channel-knowledge" id="channelKnowledgeBox">
          <div class="chconv-header channel-knowledge-header">
            <div class="channel-knowledge-title">
              <span class="chconv-title">知识沉淀</span>
              <span class="chip muted" id="channelKnowledgeCountChip">0条</span>
            </div>
            <button class="btn" id="channelKnowledgeToggleBtn" type="button">展开</button>
          </div>
          <div class="chknow-list" id="channelKnowledgeList"></div>
        </div>
      </main>

      <!-- 右侧：详情区（任务详情/对话详情） -->
      <section class="detail-view" id="detailView">
        <!-- 移动端返回按钮 -->
        <button class="back-to-list" id="backToList" title="返回列表">
          <svg viewBox="0 0 24 24" fill="none" width="18" height="18">
            <path d="M15 19l-7-7 7-7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span>返回</span>
        </button>
        <div class="detailh">
          <div class="detailh-main">
            <div class="dt" id="detailTitle">未选择事项</div>
            <div class="dsub" id="detailSub"></div>
            <div class="dpathbar" id="detailPathBar" style="display:none;">
              <div class="p" id="detailPathText" title="点击复制路径"></div>
              <button class="iconbtn" id="detailRevealBtn" title="在 Finder 中打开">
                <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path d="M3.5 7.5c0-1.1.9-2 2-2h4.1c.5 0 1 .2 1.4.6l.9.9c.2.2.4.3.7.3h6.8c1.1 0 2 .9 2 2v7.2c0 1.1-.9 2-2 2H5.5c-1.1 0-2-.9-2-2V7.5Z" stroke="currentColor" stroke-width="1.5"/>
                  <path d="M3.5 9.2h17" stroke="currentColor" stroke-width="1.5" opacity="0.55"/>
                </svg>
              </button>
            </div>
          </div>
          <div class="detailh-actions">
            <button class="btn icon-text-btn" id="detailFilesBtn" title="查看当前会话提及过的文件" style="display:none;">
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" width="14" height="14">
                <path d="M5.5 6.5a2 2 0 0 1 2-2h3.7c.5 0 1 .2 1.4.6l.8.8c.2.2.4.3.7.3h2.4a2 2 0 0 1 2 2v8.2a2 2 0 0 1-2 2H7.5a2 2 0 0 1-2-2V6.5Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>
                <path d="M8.5 10.2h7M8.5 13.2h5.4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
              </svg>
              <span class="detail-files-count-total" id="detailFilesCountTotal" style="display:none;">0</span>
              <span class="detail-files-count-star" id="detailFilesCountStarWrap" style="display:none;">
                <span class="detail-files-count-star-icon">★</span>
                <span id="detailFilesCountStar">0</span>
              </span>
            </button>
            <button class="btn icon-text-btn" id="detailMemoBtn" title="会话需求暂存与备忘" style="display:none;">
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" width="14" height="14">
                <path d="M7 4.5h10a2 2 0 0 1 2 2v11l-4-2.4-4 2.4-4-2.4-4 2.4v-11a2 2 0 0 1 2-2h2" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M9 8h6M9 11h5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
              </svg>
              <span class="memo-count-dot memo" id="detailMemoCountDot" style="display:none;">0</span>
            </button>
            <button class="btn icon-text-btn" id="detailTaskTrackingBtn" title="查看当前会话任务" style="display:none;">
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" width="14" height="14">
                <path d="M6 6.5h12" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>
                <path d="M6 11.5h8" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>
                <path d="M6 16.5h6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>
                <path d="M17.4 15.8 19.6 18l-4.1 4-2.1-2.2 4-4Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
              </svg>
              <span>任务</span>
            </button>
            <button class="btn icon-text-btn" id="detailTaskPushBtn" title="协作派发" style="display:none;">
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" width="14" height="14">
                <path d="M5 12h10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
                <path d="M11 6l6 6-6 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              <span>协作派发</span>
            </button>
          </div>
        </div>
        <div class="detailb">
          <div class="chips" id="detailMeta" style="justify-content:flex-start;"></div>
          <div id="detailExcerpt" class="mdview">(点击任意事项卡片，在此查看详情)</div>
          <div class="items" id="detailMore"></div>
          <!-- CCB 区块 -->
          <section class="ccb" id="ccbBox">
            <div class="ccbh">
              <h3 class="t">通道对话（CCB）</h3>
              <div class="chips" style="justify-content:flex-end; gap:8px;">
                <span class="chip muted" id="ccbSidChip" style="display:none;"></span>
                <button class="btn" id="ccbTokenBtn" title="设置/清除 Token">Token</button>
                <button class="btn primary" id="ccbNewConvBtn" title="创建新的 CLI 会话">新增对话</button>
                <button class="btn primary" id="ccbBindBtn" style="display:none;" title="为当前通道绑定 session_id">绑定对话</button>
                <button class="btn" id="ccbCopySidBtn" style="display:none;" title="复制 session_id">复制ID</button>
                <button class="btn" id="ccbEditBindBtn" style="display:none;" title="修改绑定">改绑</button>
                <button class="btn danger" id="ccbUnbindBtn" style="display:none;" title="清除绑定">解绑</button>
                <button class="btn" id="ccbRefreshBtn" title="刷新对话回溯">刷新</button>
              </div>
            </div>
            <div class="ccbb">
              <div class="hint" id="ccbHint">在此向该通道绑定的 CLI session 发送消息，并实时查看处理过程与最后回复。</div>
              <div class="ccbsend">
                <div class="msg-input-wrap">
                  <textarea class="msg-input" id="ccbMsg" placeholder="输入要发给该通道 CLI 的消息（Enter 发送，Shift+Enter 换行）" rows="1"></textarea>
                </div>
                <button class="btn primary" id="ccbSendBtn">发送</button>
              </div>
              <div class="runs" id="ccbRuns"></div>
            </div>
          </section>
          <!-- 对话区块 -->
          <section class="convwrap" id="convWrap">
            <div class="convtimeline" id="convTimeline"></div>
            <div class="convtrainingdock" id="convTrainingDock" aria-hidden="true">
              <div class="convtraining" id="convTraining" style="display:none;">
                <div class="convtraining-ico" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none">
                    <path d="M4 8.8 12 5l8 3.8-8 3.8L4 8.8Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>
                    <path d="M7 11.4V15c0 .9 2 2.4 5 2.4s5-1.5 5-2.4v-3.6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>
                  </svg>
                </div>
                <div class="convtraining-main">
                  <div class="convtraining-title-row">
                    <span class="convtraining-title">Agent培训</span>
                    <span class="convtraining-count" id="convTrainingCount">再 1 条消息后自动消失</span>
                  </div>
                  <div class="convtraining-desc" id="convTrainingDesc">新 Agent 开始协作前，先学习项目 skills、发消息方式与回执规则，并完成一次通讯录正式发送验证。</div>
                </div>
                <div class="convtraining-actions">
                  <button class="btn primary convtraining-send" id="convTrainingSendBtn" type="button">发送培训</button>
                  <button class="convtraining-close" id="convTrainingCloseBtn" type="button" aria-label="关闭培训提醒" title="关闭">×</button>
                </div>
              </div>
            </div>
            <div class="convcomposer">
              <div class="convsenderrow" id="convSenderRow">
                <div class="convsendermeta">
                  <div class="convsenderhint" id="convSenderHint"></div>
                  <div class="convhint" id="convHint">在该会话下继续发送消息，系统会按 5 秒频率自动刷新处理状态。</div>
                </div>
                <div class="convsenderactions">
                  <button class="conv-training-toggle" id="convTrainingReopenBtn" type="button" title="重新显示 Agent 培训" aria-label="重新显示 Agent 培训" style="display:none;">
                    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <path d="M4 8.8 12 5l8 3.8-8 3.8L4 8.8Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>
                      <path d="M7 11.4V15c0 .9 2 2.4 5 2.4s5-1.5 5-2.4v-3.6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>
                    </svg>
                  </button>
                  <button class="convrecentagents-global-toggle active" id="convRecentAgentsGlobalToggle" type="button" title="已显示最近联系，点击隐藏" aria-label="隐藏最近联系" aria-pressed="true">
                    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <path d="M8 11.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4Z" stroke="currentColor" stroke-width="1.6"/>
                      <path d="M16.8 10.1a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z" stroke="currentColor" stroke-width="1.5" opacity="0.72"/>
                      <path d="M4.5 18.2c.6-2.4 2.6-3.9 5.1-3.9s4.4 1.5 5 3.9" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
                      <path d="M14.4 17.1c.4-1.6 1.8-2.6 3.4-2.6 1 0 1.9.4 2.5 1.2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" opacity="0.72"/>
                    </svg>
                    <span class="convrecentagents-global-toggle-count" aria-hidden="true" hidden></span>
                  </button>
                  <button class="conv-enter-send-toggle active" id="convEnterSendToggle" type="button" title="已启用回车发送，点击关闭" aria-label="关闭回车发送" aria-pressed="true">
                    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <rect x="3.5" y="6.5" width="17" height="11" rx="3" stroke="currentColor" stroke-width="1.6"/>
                      <path d="M6.8 10.1h1.6M10 10.1h1.6M13.2 10.1h1.6M16.4 10.1h1.2M6.8 13.6h3.8M11.6 13.6h5.8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                      <path class="kbd-slash" d="M5 19 19 5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
                    </svg>
                  </button>
                </div>
              </div>
              <div class="convreply" id="convReplyContext" style="display:none;"></div>
              <div class="convquicktips" id="convQuickTips"></div>
              <div class="convrecentagents" id="convRecentAgents" style="display:none;"></div>
              <div class="convmentions" id="convMentions"></div>
              <div class="convattachments" id="convAttachments"></div>
              <div class="convsend">
                <input type="file" id="convFileInput" multiple style="display:none" />
                <button class="btn" id="convUploadBtn" title="上传附件">📎</button>
                <div class="msg-input-wrap">
                  <textarea class="msg-input" id="convMsg" placeholder="输入要发给该会话的消息（Enter 发送，Shift+Enter 换行）" rows="1"></textarea>
                </div>
                <button class="btn" id="convMemoSaveBtn" title="记录到会话备忘">记录</button>
                <button class="btn primary" id="convSendBtn">发送</button>
              </div>
            </div>
          </section>
        </div>
      </section>
    </div>
  </div>

  <div class="memo-drawer-mask" id="convMemoDrawerMask" role="dialog" aria-modal="true" aria-label="会话备忘抽屉">
    <aside class="memo-drawer" role="document">
      <div class="memo-drawer-head">
        <div>
          <div class="memo-drawer-title">会话备忘</div>
          <div class="memo-drawer-sub" id="convMemoDrawerSub">当前会话暂无备忘</div>
        </div>
        <button class="btn" id="convMemoCloseBtn" type="button">关闭</button>
      </div>
      <div class="memo-drawer-ops">
        <button class="btn" id="convMemoSelectAllBtn" type="button">全选</button>
        <button class="btn" id="convMemoApplyBtn" type="button">放入</button>
        <button class="btn danger" id="convMemoApplyDeleteBtn" type="button">放入删</button>
        <button class="btn primary" id="convMemoSendDeleteBtn" type="button">发并删</button>
        <button class="btn danger" id="convMemoDeleteBtn" type="button">删选中</button>
        <button class="btn danger" id="convMemoClearBtn" type="button">清空</button>
      </div>
      <div class="hint memo-drawer-hint" id="convMemoHint">将当前输入区内容点击“记录”后可在这里管理。</div>
      <div class="memo-drawer-list" id="convMemoList"></div>
    </aside>
  </div>

  <div class="memo-drawer-mask" id="convFileDrawerMask" role="dialog" aria-modal="true" aria-label="会话文件抽屉">
    <aside class="memo-drawer conv-file-drawer" role="document">
      <div class="memo-drawer-head">
        <div>
          <div class="memo-drawer-title">会话文件</div>
          <div class="memo-drawer-sub" id="convFileDrawerSub">当前会话暂无文件提及</div>
        </div>
        <button class="btn" id="convFileCloseBtn" type="button">关闭</button>
      </div>
      <div class="memo-drawer-ops">
        <button class="btn" id="convFileRefreshBtn" type="button">刷新</button>
        <button class="btn" id="convFileOnlyStarredBtn" type="button">仅收藏</button>
        <label class="conv-file-sort">
          <span>排序</span>
          <select class="input conv-file-sort-select" id="convFileSortSelect">
            <option value="time_desc">时间↓</option>
            <option value="time_asc">时间↑</option>
            <option value="mention_desc">提及↓</option>
            <option value="name_asc">名称↑</option>
          </select>
        </label>
      </div>
      <div class="conv-file-filterbar" id="convFileTypeFilterBar"></div>
      <div class="hint memo-drawer-hint" id="convFileHint">这里会汇总当前会话消息里已经提及过的文件、附件与分享页。</div>
      <div class="memo-drawer-list conv-file-drawer-list" id="convFileList"></div>
    </aside>
  </div>

  <div class="memo-drawer-mask conv-task-drawer-mask" id="convTaskDrawerMask" role="dialog" aria-modal="true" aria-label="会话任务抽屉">
    <aside class="memo-drawer conv-task-drawer" role="document">
      <div class="memo-drawer-head">
        <div>
          <div class="memo-drawer-title">会话任务</div>
          <div class="memo-drawer-sub" id="convTaskDrawerSub">当前会话暂无任务跟踪</div>
        </div>
        <button class="btn" id="convTaskCloseBtn" type="button">关闭</button>
      </div>
      <div class="hint memo-drawer-hint conv-task-drawer-hint" id="convTaskHint">这里会展示当前任务、相关任务，以及每条任务最近的一次活动。</div>
      <div class="memo-drawer-list conv-task-drawer-list" id="convTaskDrawerList"></div>
    </aside>
  </div>

  <!-- 全局协作消息派发弹窗 -->
  <div class="bmask" id="taskPushMask" role="dialog" aria-modal="true" aria-label="协作消息派发">
    <div class="bmodal task-push-modal" role="document">
      <div class="bmodalh">
        <div class="t">协作消息派发</div>
        <div class="s" id="taskPushModalSub">统一协作消息派发入口（立即/定时）</div>
      </div>
      <div class="bmodalb">
        <div id="taskPushModalBody"></div>
      </div>
      <div class="bmodalf">
        <button class="btn" id="taskPushCloseBtn">关闭</button>
      </div>
    </div>
  </div>

  <!-- 绑定对话弹窗 -->
  <div class="bmask" id="bindMask" role="dialog" aria-modal="true" aria-label="绑定对话">
    <div class="bmodal" role="document">
      <div class="bmodalh">
        <div class="t">绑定通道对话</div>
        <div class="s" id="bindSub">-</div>
      </div>
      <div class="bmodalb">
        <div style="display:grid; gap:10px;">
          <div style="display:grid; gap:6px;">
            <label for="bindCliType">CLI 类型</label>
            <select class="input" id="bindCliType" style="cursor:pointer;">
              <option value="codex">Codex CLI</option>
              <option value="claude">Claude Code</option>
              <option value="opencode">OpenCode</option>
            </select>
          </div>
          <div style="display:grid; gap:6px;">
            <label for="bindSid">Session ID</label>
            <input class="input" id="bindSid" placeholder="例如：019bde9b-4793-70e0-b18a-a437279b2d18 或 ses_abc123..." />
          </div>
          <div class="berr" id="bindErr" style="display:none;"></div>
        </div>
        <div class="hint">该绑定已保存在本机磁盘（<code>.sessions/</code> 目录），清除浏览器缓存后仍然有效。</div>
      </div>
      <div class="bmodalf">
        <button class="btn" id="bindCreateBtn" title="在本机创建一个新的 session">创建新对话</button>
        <button class="btn" id="bindCancelBtn">取消</button>
        <button class="btn primary" id="bindSaveBtn">保存绑定</button>
      </div>
    </div>
  </div>

  <!-- 新增/接入对话弹窗 -->
  <div class="bmask" id="newConvMask" role="dialog" aria-modal="true" aria-label="接入对话">
    <div class="bmodal newconv-modal" role="document">
      <div class="bmodalh">
        <div class="t">接入通道对话</div>
        <div class="s" id="newConvSub">创建新会话或绑定已有会话 ID</div>
      </div>
      <div class="bmodalb">
        <div class="newconv-mode" role="tablist" aria-label="接入方式">
          <button class="newconv-mode-btn active" id="newConvModeCreate" data-mode="create" type="button">新建对话</button>
          <button class="newconv-mode-btn" id="newConvModeAttach" data-mode="attach" type="button">添加已有对话</button>
        </div>
        <div class="newconv-fields">
          <div class="newconv-field">
            <label for="newConvProject">项目</label>
            <select class="input" id="newConvProject" style="cursor:pointer;"></select>
          </div>
          <div class="newconv-field">
            <label for="newConvChannel">通道</label>
            <select class="input" id="newConvChannel" style="cursor:pointer;"></select>
          </div>
          <div class="newconv-field">
            <label for="newConvCliType">CLI 类型</label>
            <select class="input" id="newConvCliType" style="cursor:pointer;">
              <option value="codex">Codex CLI</option>
              <option value="claude">Claude Code</option>
              <option value="opencode">OpenCode</option>
              <option value="gemini">Gemini CLI</option>
            </select>
          </div>
          <div class="newconv-field">
            <label for="newConvAlias">对话agent名称（alias，可选）</label>
            <input class="input" id="newConvAlias" placeholder="例如：服务开发-通讯能力" />
          </div>
          <div class="newconv-field">
            <label for="newConvSessionRole">会话角色</label>
            <select class="input" id="newConvSessionRole" style="cursor:pointer;">
              <option value="child">子会话</option>
              <option value="primary">主会话</option>
            </select>
          </div>
          <section class="newconv-advanced" id="newConvAdvancedSection">
            <button
              class="newconv-advanced-toggle"
              id="newConvAdvancedToggle"
              type="button"
              aria-expanded="false"
              aria-controls="newConvAdvancedBody"
            >
              <span class="newconv-advanced-copy">
                <span class="newconv-advanced-title">高级配置</span>
                <span class="newconv-advanced-summary" id="newConvAdvancedSummary">默认：总是新建 / stable</span>
              </span>
              <span class="newconv-advanced-caret" aria-hidden="true">▾</span>
            </button>
            <div class="newconv-advanced-body" id="newConvAdvancedBody" hidden>
              <div class="newconv-field">
                <label for="newConvModel">模型（可选）</label>
                <input class="input" id="newConvModel" placeholder="留空使用该 CLI 默认模型" />
              </div>
              <div class="newconv-field">
                <label for="newConvPurpose">用途说明（可选）</label>
                <input class="input" id="newConvPurpose" placeholder="例如：补位处理子级07关系图重构" />
              </div>
              <div class="newconv-field">
                <label for="newConvReuseStrategy">创建策略</label>
                <select class="input" id="newConvReuseStrategy" style="cursor:pointer;">
                  <option value="create_new">总是新建</option>
                  <option value="reuse_active">优先复用同环境活跃会话</option>
                  <option value="rotate">新建并准备轮换</option>
                </select>
              </div>
              <div class="newconv-field">
                <label for="newConvEnvironment">环境</label>
                <select class="input" id="newConvEnvironment" style="cursor:pointer;"></select>
              </div>
              <div class="newconv-field">
                <label for="newConvWorktreeRoot">worktree 根目录</label>
                <input class="input" id="newConvWorktreeRoot" placeholder="/abs/path/to/worktree" />
              </div>
              <div class="newconv-field">
                <label for="newConvWorkdir">workdir</label>
                <input class="input" id="newConvWorkdir" placeholder="/abs/path/to/workdir" />
              </div>
              <div class="newconv-field">
                <label for="newConvBranch">branch</label>
                <input class="input" id="newConvBranch" placeholder="release/... 或 refactor/..." />
              </div>
            </div>
          </section>
          <div class="newconv-field" id="newConvSessionRow" style="display:none;">
            <label for="newConvSessionId">Session ID</label>
            <input class="input" id="newConvSessionId" placeholder="例如：019bde9b-4793-70e0-b18a-a437279b2d18 或 ses_abc123..." />
            <div class="hint" style="margin-top:0;">输入已有会话 ID，系统会直接绑定到当前项目通道。</div>
          </div>
          <div class="newconv-field" id="newConvInitRow" style="display:grid;">
            <label for="newConvInitMessage">创建后自动发送消息（可编辑）</label>
            <textarea class="input nctextarea" id="newConvInitMessage" placeholder="请输入创建后需要自动发送的首条消息"></textarea>
            <div class="hint" style="margin-top:0;">仅在“新建对话”模式生效；“添加已有对话”模式不自动发送。</div>
          </div>
          <div class="berr" id="newConvErr" style="display:none;"></div>
        </div>
        <div class="hint" id="newConvHint">将创建新的 CLI 会话并自动绑定到通道。</div>
      </div>
      <div class="bmodalf">
        <button class="btn" id="newConvCancelBtn">取消</button>
        <button class="btn primary" id="newConvCreateBtn">创建并绑定</button>
      </div>
    </div>
  </div>

  <!-- 会话信息弹窗 -->
  <div class="bmask" id="convSessionInfoMask" role="dialog" aria-modal="true" aria-label="会话基本信息">
    <div class="bmodal conv-session-info-modal" role="document">
      <div class="bmodalh">
        <div class="t">会话基本信息</div>
        <div class="s" id="convSessionInfoSub">-</div>
      </div>
      <div class="bmodalb">
        <div id="convSessionInfoBody"></div>
        <div class="berr" id="convSessionInfoErr" style="display:none;"></div>
      </div>
      <div class="bmodalf conv-session-info-footer">
        <div id="convSessionInfoStatusSlot" class="conv-session-status-slot"></div>
        <div class="conv-session-info-footer-actions">
          <button class="btn" id="convSessionInfoCancelBtn">取消</button>
          <button class="btn primary" id="convSessionInfoSaveBtn">保存</button>
        </div>
      </div>
    </div>
  </div>

  <!-- 会话头像选择弹窗 -->
  <div class="bmask" id="convAvatarPickerMask" role="dialog" aria-modal="true" aria-label="选择会话头像">
    <div class="bmodal conv-avatar-picker-modal" role="document">
      <div class="bmodalh">
        <div class="t">选择头像</div>
        <div class="s" id="convAvatarPickerSub">为当前会话分配一个更易识别的头像</div>
      </div>
      <div class="bmodalb">
        <div id="convAvatarPickerBody"></div>
        <div class="berr" id="convAvatarPickerErr" style="display:none;"></div>
      </div>
      <div class="bmodalf">
        <div class="hint" id="convAvatarPickerHint" style="margin:0;">头像配置本轮仅保存在本地浏览器，优先按 session_id 精确匹配。</div>
        <div class="conv-session-info-footer-actions">
          <button class="btn" id="convAvatarPickerCancelBtn">取消</button>
          <button class="btn primary" id="convAvatarPickerConfirmBtn">确认选择</button>
        </div>
      </div>
    </div>
  </div>

  <!-- 通道对话管理弹窗 -->
  <div class="bmask" id="channelConvManageMask" role="dialog" aria-modal="true" aria-label="通道对话管理">
    <div class="bmodal channel-conv-manage-modal" role="document">
      <div class="bmodalh">
        <div class="t">通道对话管理</div>
        <div class="s" id="channelConvManageSub">为当前通道显式指定主对话，并管理标记删除状态</div>
      </div>
      <div class="bmodalb">
        <div id="channelConvManageBody"></div>
        <div class="berr" id="channelConvManageErr" style="display:none;"></div>
      </div>
      <div class="bmodalf">
        <div class="hint" id="channelConvManageHint" style="margin:0;">每个通道仅允许一个主对话；标记删除不会清空历史消息。</div>
        <div class="conv-session-info-footer-actions">
          <button class="btn" id="channelConvManageCancelBtn">取消</button>
          <button class="btn primary" id="channelConvManageSaveBtn">保存调整</button>
        </div>
      </div>
    </div>
  </div>

  <!-- 新增通道弹窗 -->
  <div class="bmask new-channel-mask" id="newChannelMask" role="dialog" aria-modal="true" aria-label="新增通道">
    <div class="bmodal new-channel-modal" role="document">
      <div class="new-channel-head">
        <div class="new-channel-head-main">
          <div class="t">新增通道</div>
          <div class="s" id="newChannelSub">创建空通道框架，或发起 Agent 辅助创建</div>
        </div>
        <button class="icon-btn new-channel-close" id="newChannelHeaderCloseBtn" type="button" aria-label="关闭新增通道弹窗">×</button>
      </div>
      <div class="new-channel-mode-switch" role="tablist" aria-label="创建方式切换">
        <button class="new-channel-mode-btn active" id="newChannelModeDirectBtn" type="button" data-new-channel-mode="direct" aria-selected="true">直接创建</button>
        <button class="new-channel-mode-btn" id="newChannelModeAgentBtn" type="button" data-new-channel-mode="agent_assist" aria-selected="false">Agent辅助创建</button>
      </div>
      <div class="new-channel-body">
        <section class="new-channel-section new-channel-base-section">
          <div class="new-channel-section-head">
            <div>
              <div class="new-channel-section-title">基础信息</div>
              <div class="new-channel-section-desc">两种模式都会先用这里生成通道名，并创建空通道框架。</div>
            </div>
          </div>
          <div class="ncgrid ncgrid-2">
            <div class="ncfield">
              <label for="newChannelKind">通道类型（推荐） <span style="color:var(--bad);">*</span></label>
              <select class="input" id="newChannelKind" onchange="handleNewChannelFormFieldChange()">
                <option value="业务">业务</option>
                <option value="辅助">辅助</option>
                <option value="主体">主体</option>
                <option value="__custom__">其他（自定义）</option>
              </select>
            </div>
            <div class="ncfield">
              <label for="newChannelIndex">通道编号 <span style="color:var(--bad);">*</span></label>
              <input class="input" id="newChannelIndex" placeholder="例如：04 / A03" oninput="handleNewChannelFormFieldChange()" />
            </div>
          </div>
          <div class="ncfield new-channel-kind-custom" id="newChannelKindCustomWrap" style="display:none;">
            <label for="newChannelKindCustom">自定义类型名称 <span style="color:var(--bad);">*</span></label>
            <input class="input" id="newChannelKindCustom" placeholder="例如：产品 / 设计 / 运营 / 数据" oninput="handleNewChannelFormFieldChange()" />
          </div>
          <div class="ncfield">
            <label for="newChannelName">业务主题 <span style="color:var(--bad);">*</span></label>
            <input class="input" id="newChannelName" placeholder="例如：前端体验（task-overview 页面交互）" oninput="handleNewChannelFormFieldChange()" />
          </div>
          <div class="ncfield">
            <label for="newChannelDesc">通道说明（可选）</label>
            <textarea class="input nctextarea" id="newChannelDesc" placeholder="补充通道用途、边界或命名说明" oninput="handleNewChannelFormFieldChange()"></textarea>
          </div>
        </section>

        <section class="new-channel-panel active" id="newChannelDirectPanel" data-new-channel-mode="direct">
          <div class="new-channel-section new-channel-summary">
            <div class="new-channel-summary-head">
              <div class="new-channel-section-title">创建预览</div>
              <div class="new-channel-section-desc">本地即时预览，不依赖后端。</div>
            </div>
            <div class="new-channel-kv">
              <span class="k">通道名</span>
              <code id="newChannelPreviewName">-</code>
            </div>
            <div class="new-channel-kv">
              <span class="k">创建内容</span>
              <div class="v" id="newChannelPreviewDirectItems">空通道框架 / README / 沟通-收件箱 / 基础目录</div>
            </div>
            <div class="new-channel-kv">
              <span class="k">不会创建</span>
              <div class="v" id="newChannelPreviewDirectSkip">主任务 / 主对话 / Agent</div>
            </div>
          </div>
        </section>

        <section class="new-channel-panel" id="newChannelAgentPanel" data-new-channel-mode="agent_assist">
          <div class="new-channel-section">
            <div class="new-channel-section-head">
              <div>
                <div class="new-channel-section-title">选择处理 Agent</div>
                <div class="new-channel-section-desc">默认优先辅助01主会话，没有则退到首个可用主会话。</div>
              </div>
            </div>
            <div class="agent-picker" id="newChannelAgentPicker">
              <button class="agent-card" id="newChannelAgentCard" type="button" aria-haspopup="listbox" aria-expanded="false">
                <div class="agent-card-head">
                  <span class="agent-name" id="newChannelAgentName">-</span>
                  <span class="agent-tag" id="newChannelAgentTag">主会话</span>
                </div>
                <div class="agent-card-meta">
                  <span class="agent-meta" id="newChannelAgentMeta">正在加载可选 Agent…</span>
                  <span class="agent-caret">▾</span>
                </div>
              </button>
              <div class="agent-menu" id="newChannelAgentMenu" role="listbox" aria-label="处理 Agent 选择列表"></div>
            </div>
            <div class="hint" id="newChannelAgentHint" style="margin-top:8px;">选择后将创建通道并正式派发给该 Agent。</div>
          </div>

          <div class="new-channel-section">
            <div class="new-channel-section-head">
              <div>
                <div class="new-channel-section-title">业务要求说明</div>
                <div class="new-channel-section-desc">只保留这一条输入，尽量把边界、目标和例外说清楚。</div>
              </div>
            </div>
            <textarea class="input nctextarea new-channel-requirement" id="newChannelRequirement" placeholder="例如：我想新增一个通道，只保留空通道框架创建，不要创建主任务或主对话；Agent 辅助时先整理命名、范围和基础目录，再回传结果。" oninput="handleNewChannelFormFieldChange()"></textarea>
          </div>
        </section>

        <section class="new-channel-result" id="newChannelResult" style="display:none;">
          <div class="new-channel-section-head">
            <div>
              <div class="new-channel-section-title">结果摘要</div>
              <div class="new-channel-section-desc">这里展示创建或派发后的最小结果。</div>
            </div>
          </div>
          <div class="new-channel-result-body" id="newChannelResultBody"></div>
        </section>

        <div class="berr" id="newChannelErr" style="display:none;"></div>
      </div>
      <div class="new-channel-foot">
        <div class="hint" id="newChannelFootNote">直接创建只生成空通道框架，不创建主任务或主对话。</div>
        <div class="new-channel-foot-actions">
          <button class="btn" id="newChannelCancelBtn" type="button">取消</button>
          <button class="btn" id="newChannelReloadBtn" style="display:none;" type="button">刷新页面</button>
          <button class="btn primary" id="newChannelCreateBtn" type="button">开始创建</button>
        </div>
      </div>
    </div>
  </div>

  <!-- 通道管理：找 Agent 编辑 -->
  <div class="bmask" id="channelEditAgentMask" role="dialog" aria-modal="true" aria-label="找 Agent 编辑">
    <div class="bmodal channel-manage-modal" role="document">
      <div class="bmodalh">
        <div class="t">找 Agent 编辑</div>
        <div class="s" id="channelEditAgentSub">-</div>
      </div>
      <div class="bmodalb channel-manage-body">
        <section class="channel-manage-section channel-manage-summary">
          <div class="channel-manage-section-title">当前通道</div>
          <div class="channel-manage-kv">
            <span class="k">通道名</span>
            <code class="v" id="channelEditAgentName">-</code>
          </div>
          <div class="channel-manage-kv">
            <span class="k">当前说明</span>
            <div class="v" id="channelEditAgentDesc">-</div>
          </div>
        </section>

        <section class="channel-manage-section">
          <div class="channel-manage-section-head">
            <div>
              <div class="channel-manage-section-title">选择处理 Agent</div>
              <div class="channel-manage-section-desc">默认优先辅助01主会话，没有则退到首个可用主会话。</div>
            </div>
          </div>
          <div class="agent-picker" id="channelEditAgentPicker">
            <button class="agent-card" id="channelEditAgentCard" type="button" aria-haspopup="listbox" aria-expanded="false">
              <div class="agent-card-head">
                <span class="agent-name" id="channelEditAgentCardName">-</span>
                <span class="agent-tag" id="channelEditAgentCardTag">主会话</span>
              </div>
              <div class="agent-card-meta">
                <span class="agent-meta" id="channelEditAgentCardMeta">正在加载可选 Agent…</span>
                <span class="agent-caret">▾</span>
              </div>
            </button>
            <div class="agent-menu" id="channelEditAgentMenu" role="listbox" aria-label="处理 Agent 选择列表"></div>
          </div>
        </section>

        <section class="channel-manage-section">
          <div class="channel-manage-section-head">
            <div>
              <div class="channel-manage-section-title">业务要求说明</div>
              <div class="channel-manage-section-desc">用于补充这次希望 Agent 处理的内容与边界。</div>
            </div>
          </div>
          <textarea class="input nctextarea channel-manage-textarea" id="channelEditAgentRequirement" placeholder="例如：请帮我补齐通道说明、边界和 README 索引；不要改名、改编号或删除通道。"></textarea>
        </section>

        <section class="channel-manage-result" id="channelEditAgentResult" style="display:none;">
          <div class="channel-manage-section-head">
            <div>
              <div class="channel-manage-section-title">发送结果</div>
              <div class="channel-manage-section-desc">这里显示正式派发后的最小摘要。</div>
            </div>
          </div>
          <div class="channel-manage-result-body" id="channelEditAgentResultBody"></div>
        </section>

        <div class="berr" id="channelEditAgentErr" style="display:none;"></div>
      </div>
      <div class="bmodalf channel-manage-footer">
        <button class="btn" id="channelEditAgentCancelBtn" type="button">取消</button>
        <button class="btn primary" id="channelEditAgentSubmitBtn" type="button">发送给 Agent 处理</button>
      </div>
    </div>
  </div>

  <!-- 通道管理：发送确认 -->
  <div class="bmask" id="channelEditAgentConfirmMask" role="dialog" aria-modal="true" aria-label="确认发送给 Agent">
    <div class="bmodal channel-manage-confirm-modal" role="document">
      <div class="bmodalh">
        <div class="t">确认发送</div>
        <div class="s">会通过正式系统消息派发给所选 Agent</div>
      </div>
      <div class="bmodalb">
        <div class="channel-manage-kv">
          <span class="k">当前通道</span>
          <div class="v" id="channelEditAgentConfirmChannel">-</div>
        </div>
        <div class="channel-manage-kv">
          <span class="k">处理 Agent</span>
          <div class="v" id="channelEditAgentConfirmTarget">-</div>
        </div>
        <div class="hint">确认后会创建正式 run，并按标准协作消息字段派发。</div>
        <div class="berr" id="channelEditAgentConfirmErr" style="display:none;"></div>
      </div>
      <div class="bmodalf">
        <button class="btn" id="channelEditAgentConfirmCancelBtn" type="button">返回</button>
        <button class="btn primary" id="channelEditAgentConfirmSubmitBtn" type="button">确认发送</button>
      </div>
    </div>
  </div>

  <!-- 通道管理：删除确认 -->
  <div class="bmask" id="channelDeleteMask" role="dialog" aria-modal="true" aria-label="删除通道">
    <div class="bmodal channel-delete-modal" role="document">
      <div class="bmodalh">
        <div class="t">删除通道</div>
        <div class="s">删除前需要再次确认，避免误删</div>
      </div>
      <div class="bmodalb channel-manage-body">
        <section class="channel-manage-section channel-manage-summary">
          <div class="channel-manage-section-title">删除范围</div>
          <div class="channel-manage-kv">
            <span class="k">通道名</span>
            <code class="v" id="channelDeleteName">-</code>
          </div>
          <div class="channel-manage-kv">
            <span class="k">当前说明</span>
            <div class="v" id="channelDeleteDesc">-</div>
          </div>
        </section>
        <div class="channel-delete-warning">
          会删除该通道目录及配套文件夹，并清理相关会话绑定；不会删除运行历史记录。
        </div>
        <div class="ncfield">
          <label for="channelDeleteConfirmInput">请输入完整通道名确认删除</label>
          <input class="input" id="channelDeleteConfirmInput" placeholder="请完整输入当前通道名" />
        </div>
        <div class="berr" id="channelDeleteErr" style="display:none;"></div>
      </div>
      <div class="bmodalf">
        <button class="btn" id="channelDeleteCancelBtn" type="button">取消</button>
        <button class="btn primary channel-delete-confirm-btn" id="channelDeleteConfirmBtn" type="button">确认删除</button>
      </div>
    </div>
  </div>

  <script id="data" type="application/json">__PAYLOAD__</script>
  <script>
__INLINE_JS__
  </script>

  </body>
</html>
