    const TASK_OBSERVATORY_PAGE_SIZE = 10;
    const TASK_OBSERVATORY_STYLE_ID = "taskObservatoryModeStylesV1";
    const TASK_OBSERVATORY_UI = {
      detailRequestedByProject: Object.create(null),
      visibleLimitByProject: Object.create(null),
      specialFilterByProject: Object.create(null),
    };

    function taskObservatoryProjectKey(projectId = "") {
      const direct = String(projectId || "").trim();
      if (direct) return direct;
      const currentProject = (typeof STATE === "object" && STATE) ? String(STATE.project || "").trim() : "";
      return currentProject;
    }

    function taskObservatorySessionNeedsCreatedAtHydration(session) {
      const tracking = typeof normalizeTaskTrackingClient === "function"
        ? normalizeTaskTrackingClient(session && session.task_tracking)
        : null;
      if (!tracking || !tracking.current_task_ref) return false;
      return false;
    }

    function taskObservatoryShouldLoadDetailForSession(session, projectId = "") {
      const row = (session && typeof session === "object") ? session : {};
      const sessionId = String(row.id || row.session_id || "").trim();
      if (!sessionId) return false;
      const pid = taskObservatoryProjectKey(projectId);
      if (!pid || pid === "overview") return false;
      if (sessionId === String((typeof STATE === "object" && STATE && STATE.selectedSessionId) || "").trim()) return false;
      if (taskObservatorySessionNeedsCreatedAtHydration(row)) return true;
      const ui = (typeof TASK_OBSERVATORY_UI === "object" && TASK_OBSERVATORY_UI) ? TASK_OBSERVATORY_UI : null;
      const requestedByProject = ui && ui.detailRequestedByProject && typeof ui.detailRequestedByProject === "object"
        ? ui.detailRequestedByProject
        : null;
      const requested = requestedByProject && requestedByProject[pid] && typeof requestedByProject[pid] === "object"
        ? requestedByProject[pid]
        : null;
      return !!(requested && requested[sessionId]);
    }

    function taskObservatoryScheduleDetailLoads(projectId, sessions, visibleLimit = 0) {
      if (typeof ensureConversationSessionDetailLoaded !== "function") return [];
      const pid = taskObservatoryProjectKey(projectId);
      if (!pid || pid === "overview") return [];
      const rows = Array.isArray(sessions) ? sessions : [];
      const limit = Math.max(0, Number(visibleLimit) || 0);
      const visible = limit > 0 ? rows.slice(0, limit) : rows.slice();
      const pending = visible
        .filter((row) => taskObservatoryShouldLoadDetailForSession(row, pid))
        .map((row) => {
          const sessionId = String((row && (row.id || row.session_id)) || "").trim();
          if (!sessionId) return null;
          return Promise.resolve(ensureConversationSessionDetailLoaded(sessionId, { maxAgeMs: 15_000 }))
            .then(() => {
              if (typeof render === "function") render();
            })
            .catch(() => {});
        })
        .filter(Boolean);
      return pending;
    }

    function taskObservatoryVisibleLimit(projectId = "") {
      const pid = taskObservatoryProjectKey(projectId);
      if (!pid) return TASK_OBSERVATORY_PAGE_SIZE;
      const raw = Number(TASK_OBSERVATORY_UI.visibleLimitByProject[pid] || 0);
      return Number.isFinite(raw) && raw > 0 ? Math.max(TASK_OBSERVATORY_PAGE_SIZE, Math.round(raw)) : TASK_OBSERVATORY_PAGE_SIZE;
    }

    function resetTaskObservatoryVisibleLimit(projectId = "") {
      const pid = taskObservatoryProjectKey(projectId);
      if (!pid) return TASK_OBSERVATORY_PAGE_SIZE;
      TASK_OBSERVATORY_UI.visibleLimitByProject[pid] = TASK_OBSERVATORY_PAGE_SIZE;
      return TASK_OBSERVATORY_PAGE_SIZE;
    }

    function increaseTaskObservatoryVisibleLimit(projectId = "", step = TASK_OBSERVATORY_PAGE_SIZE) {
      const pid = taskObservatoryProjectKey(projectId);
      if (!pid) return TASK_OBSERVATORY_PAGE_SIZE;
      const current = taskObservatoryVisibleLimit(pid);
      const delta = Number.isFinite(Number(step)) ? Math.max(1, Number(step)) : TASK_OBSERVATORY_PAGE_SIZE;
      const next = current + delta;
      TASK_OBSERVATORY_UI.visibleLimitByProject[pid] = next;
      return next;
    }

    function taskObservatorySpecialFilter(projectId = "") {
      const pid = taskObservatoryProjectKey(projectId);
      if (!pid) return "";
      return String(TASK_OBSERVATORY_UI.specialFilterByProject[pid] || "").trim().toLowerCase();
    }

    function setTaskObservatoryFilter(projectId = "", lane = "全部", opts = {}) {
      const pid = taskObservatoryProjectKey(projectId);
      if (!pid) return;
      const allowed = new Set(["全部", ...taskLaneOrderList()]);
      const nextLane = allowed.has(String(lane || "").trim()) ? String(lane || "").trim() : "全部";
      const special = String((opts && opts.special) || "").trim().toLowerCase();
      STATE.taskLane = nextLane;
      TASK_OBSERVATORY_UI.specialFilterByProject[pid] = special;
      resetTaskObservatoryVisibleLimit(pid);
      setHash();
      render();
    }

    function taskObservatoryRebuildUiState() {
      const state = (typeof window !== "undefined" && window.PROJECT_REBUILD_UI && typeof window.PROJECT_REBUILD_UI === "object")
        ? window.PROJECT_REBUILD_UI
        : null;
      return {
        loading: !!(state && state.loading),
        lastError: String((state && state.lastError) || "").trim(),
      };
    }

    function buildTaskObservatoryRefreshAction(projectId) {
      const state = taskObservatoryRebuildUiState();
      const wrap = el("div", { class: "task-observatory-refresh-wrap" });
      const btn = el("button", {
        type: "button",
        class: "task-observatory-refresh-btn" + (state.loading ? " is-loading" : ""),
        "aria-label": state.loading ? "正在刷新任务数据" : "刷新任务数据",
        title: "重新扫描任务规划目录，并在完成后刷新当前任务页。",
      });
      btn.disabled = state.loading;
      btn.appendChild(el("span", { class: "task-observatory-refresh-icon", "aria-hidden": "true" }));
      btn.appendChild(el("span", { text: state.loading ? "正在刷新..." : "刷新任务数据" }));
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (state.loading) return;
        if (typeof triggerProjectDashboardRebuild === "function") {
          triggerProjectDashboardRebuild();
          if (typeof render === "function") render();
          return;
        }
        alert("当前页面缺少刷新能力，请重新加载后再试。");
      });
      wrap.appendChild(btn);
      if (state.lastError) {
        wrap.appendChild(el("span", {
          class: "task-observatory-refresh-error",
          text: "刷新失败：" + state.lastError,
        }));
      }
      return wrap;
    }

    function taskObservatoryTimelineDateKey(rawValue = "") {
      const text = String(rawValue || "").trim();
      if (!text) return "未标记日期";
      const direct = text.match(/\d{4}-\d{2}-\d{2}/);
      if (direct && direct[0]) return direct[0];
      const parsed = new Date(text);
      if (Number.isFinite(parsed.getTime())) {
        const y = parsed.getFullYear();
        const m = String(parsed.getMonth() + 1).padStart(2, "0");
        const d = String(parsed.getDate()).padStart(2, "0");
        return y + "-" + m + "-" + d;
      }
      return text.slice(0, 10) || "未标记日期";
    }

    function taskObservatoryGroupHasBlocked(group) {
      const masterFlags = typeof taskStatusFlags === "function"
        ? taskStatusFlags(group && group.master)
        : {};
      if (masterFlags && masterFlags.blocked) return true;
      const children = Array.isArray(group && group.children) ? group.children : [];
      return children.some((child) => {
        const flags = typeof taskStatusFlags === "function" ? taskStatusFlags(child) : {};
        return !!(flags && flags.blocked);
      });
    }

    function buildTaskObservatoryModel(groupsAll, opts = {}) {
      const groups = Array.isArray(groupsAll) ? groupsAll.slice() : [];
      const laneFilter = String((opts && opts.laneFilter) || "全部").trim() || "全部";
      const specialFilter = String((opts && opts.specialFilter) || "").trim().toLowerCase();
      const visibleLimit = Number.isFinite(Number(opts && opts.visibleLimit))
        ? Math.max(1, Number(opts.visibleLimit))
        : TASK_OBSERVATORY_PAGE_SIZE;
      const timelineSource = groups
        .slice()
        .sort((a, b) => Number(b && b.latestTs || 0) - Number(a && a.latestTs || 0));
      let filtered = timelineSource;
      if (specialFilter === "blocked") {
        filtered = timelineSource.filter((group) => taskObservatoryGroupHasBlocked(group));
      } else if (laneFilter !== "全部") {
        filtered = timelineSource.filter((group) => String((group && group.lane) || "") === laneFilter);
      }
      const visibleGroups = filtered.slice(0, visibleLimit);
      const days = [];
      const dayMap = new Map();
      visibleGroups.forEach((group) => {
        const key = taskObservatoryTimelineDateKey((group && group.latestAt) || (group && group.master && group.master.updated_at) || "");
        if (!dayMap.has(key)) {
          const day = { key, label: key, items: [] };
          dayMap.set(key, day);
          days.push(day);
        }
        dayMap.get(key).items.push(group);
      });
      const totalTaskCount = groups.reduce((sum, group) => {
        const total = Number(group && group.total || 0);
        if (Number.isFinite(total) && total > 0) return sum + total;
        const children = Array.isArray(group && group.children) ? group.children.length : 0;
        return sum + children + ((group && group.master) ? 1 : 0);
      }, 0);
      const countLane = (lane) => groups.filter((group) => String((group && group.lane) || "") === lane).length;
      return {
        groups,
        filteredGroups: filtered,
        visibleGroups,
        visibleLimit,
        totalTaskCount,
        totalGroupCount: groups.length,
        filteredGroupCount: filtered.length,
        visibleGroupCount: visibleGroups.length,
        hasMore: filtered.length > visibleGroups.length,
        days,
        counts: {
          running: countLane("进行中"),
          todo: countLane("待办"),
          acceptance: countLane("待验收"),
          done: countLane("已完成"),
          paused: countLane("暂缓"),
          archived: countLane("已归档"),
          blocked: groups.filter((group) => taskObservatoryGroupHasBlocked(group)).length,
        },
      };
    }

    function ensureTaskObservatoryStyles() {
      if (typeof document === "undefined" || !document.head) return;
      if (document.getElementById(TASK_OBSERVATORY_STYLE_ID)) return;
      const style = document.createElement("style");
      style.id = TASK_OBSERVATORY_STYLE_ID;
      style.textContent = `
        .task-observatory-page{
          display:flex;
          flex-direction:column;
          gap:10px;
          padding:8px 14px 18px;
        }
        .task-observatory-head{
          display:flex;
          flex-direction:column;
          gap:12px;
          padding:14px 16px;
          border-radius:20px;
          border:1px solid rgba(15,23,42,0.06);
          background:linear-gradient(180deg, rgba(255,255,255,0.92), rgba(245,248,252,0.92));
          box-shadow:0 16px 36px rgba(15,23,42,0.05);
          backdrop-filter:blur(12px);
        }
        .task-observatory-head-main{
          display:flex;
          align-items:flex-end;
          justify-content:space-between;
          gap:14px 18px;
          flex-wrap:wrap;
        }
        .task-observatory-head-copy{
          display:grid;
          gap:8px;
          min-width:0;
          flex:1 1 320px;
        }
        .task-observatory-head-kicker{
          font-size:11px;
          font-weight:700;
          letter-spacing:0.08em;
          text-transform:uppercase;
          color:var(--muted2);
        }
        .task-observatory-head-title-row{
          display:flex;
          align-items:center;
          gap:10px;
          flex-wrap:wrap;
        }
        .task-observatory-head-title{
          font-size:22px;
          line-height:1.1;
          font-weight:900;
          color:var(--text);
        }
        .task-observatory-head-pill{
          display:inline-flex;
          align-items:center;
          gap:6px;
          padding:5px 10px;
          border-radius:999px;
          border:1px solid rgba(47,111,237,0.16);
          background:rgba(244,248,255,0.96);
          color:rgba(28,59,130,0.92);
          font-size:12px;
          font-weight:700;
          white-space:nowrap;
        }
        .task-observatory-head-pill.is-warn{
          border-color:rgba(234,179,8,0.18);
          background:rgba(255,248,224,0.96);
          color:#9a6200;
        }
        .task-observatory-head-meta{
          display:flex;
          flex-wrap:wrap;
          gap:8px;
        }
        .task-observatory-head-meta-item{
          display:inline-flex;
          align-items:center;
          padding:6px 10px;
          border-radius:999px;
          border:1px solid rgba(15,23,42,0.06);
          background:rgba(255,255,255,0.82);
          color:var(--muted);
          font-size:12px;
          font-weight:700;
          white-space:nowrap;
        }
        .task-observatory-board{
          border-radius:18px;
          border:1px solid rgba(0,0,0,0.06);
          background:rgba(255,255,255,0.88);
          box-shadow:0 10px 28px rgba(15,23,42,0.04);
        }
        .task-observatory-card-actions,
        .task-observatory-card-meta,
        .task-observatory-card-foot,
        .task-observatory-day-meta{
          display:flex;
          align-items:center;
          gap:8px;
          flex-wrap:wrap;
        }
        .task-observatory-stats{
          display:flex;
          align-items:center;
          gap:8px;
          flex-wrap:wrap;
          overflow:visible;
          padding:8px 10px;
          min-width:0;
          border-radius:16px;
          background:rgba(255,255,255,0.26);
        }
        .task-observatory-stat{
          border-radius:999px;
          border:1px solid rgba(0,0,0,0.06);
          background:rgba(255,255,255,0.72);
          box-shadow:none;
          padding:0 10px;
          min-height:34px;
          min-width:84px;
          display:inline-flex;
          align-items:center;
          gap:6px;
          justify-content:center;
          flex:0 0 auto;
          text-align:center;
          white-space:nowrap;
          box-sizing:border-box;
        }
        .task-observatory-stat.is-button{
          cursor:pointer;
          transition:border-color 150ms ease, box-shadow 150ms ease, transform 150ms ease, background 150ms ease;
        }
        .task-observatory-stat.is-button:hover{
          border-color:rgba(47,111,237,0.18);
          box-shadow:0 8px 18px rgba(15,23,42,0.04);
        }
        .task-observatory-stat.is-active{
          border-color:rgba(47,111,237,0.24);
          background:rgba(244,248,255,0.92);
          box-shadow:0 8px 18px rgba(47,111,237,0.06);
        }
        .task-observatory-stat-label{
          font-size:11px;
          font-weight:700;
          color:var(--muted2);
          line-height:1;
        }
        .task-observatory-stat-value{
          font-size:14px;
          color:var(--text);
          font-weight:900;
          line-height:1;
        }
        .task-observatory-refresh-wrap{
          display:inline-flex;
          align-items:center;
          gap:8px;
          flex:0 0 auto;
          margin-left:auto;
          min-height:34px;
        }
        .task-observatory-refresh-btn{
          min-height:34px;
          padding:0 12px;
          border-radius:999px;
          border:1px solid rgba(15,23,42,0.10);
          background:rgba(255,255,255,0.82);
          color:rgba(15,23,42,0.74);
          box-shadow:none;
          display:inline-flex;
          align-items:center;
          justify-content:center;
          gap:8px;
          font-size:12px;
          font-weight:800;
          white-space:nowrap;
          cursor:pointer;
          transition:transform 150ms ease, box-shadow 150ms ease, opacity 150ms ease;
        }
        .task-observatory-refresh-btn:hover:not(:disabled){
          border-color:rgba(47,111,237,0.18);
          color:rgba(28,59,130,0.92);
          background:rgba(255,255,255,0.98);
          box-shadow:0 8px 18px rgba(15,23,42,0.05);
        }
        .task-observatory-refresh-btn:disabled{
          cursor:wait;
          opacity:0.72;
        }
        .task-observatory-refresh-icon{
          width:12px;
          height:12px;
          border-radius:999px;
          border:2px solid rgba(47,111,237,0.18);
          border-top-color:rgba(47,111,237,0.78);
          box-sizing:border-box;
        }
        .task-observatory-refresh-btn.is-loading .task-observatory-refresh-icon{
          animation:taskObservatoryRefreshSpin 0.9s linear infinite;
        }
        .task-observatory-refresh-error{
          max-width:240px;
          color:#b42318;
          font-size:12px;
          font-weight:700;
          white-space:nowrap;
          overflow:hidden;
          text-overflow:ellipsis;
        }
        @keyframes taskObservatoryRefreshSpin{
          from{ transform:rotate(0deg); }
          to{ transform:rotate(360deg); }
        }
        @media (prefers-reduced-motion: reduce){
          .task-observatory-refresh-btn,
          .task-observatory-stat.is-button{
            transition:none;
          }
          .task-observatory-refresh-btn.is-loading .task-observatory-refresh-icon{
            animation:none;
          }
        }
        .task-observatory-board{
          padding:12px;
          display:flex;
          flex-direction:column;
          gap:10px;
        }
        .task-observatory-scroll{
          overflow:visible;
          padding-bottom:0;
        }
        .task-observatory-canvas{
          min-width:0;
          width:100%;
          display:flex;
          flex-direction:column;
          gap:14px;
          padding-right:0;
        }
        .task-observatory-day{
          display:flex;
          flex-direction:column;
          gap:8px;
          align-items:flex-start;
        }
        .task-observatory-day-head{
          display:flex;
          align-items:center;
          justify-content:flex-start;
          gap:8px;
          flex-wrap:wrap;
          width:fit-content;
          max-width:100%;
          padding:0 6px 0 0;
        }
        .task-observatory-day-title{
          display:inline-flex;
          align-items:center;
          gap:8px;
          font-size:15px;
          font-weight:900;
          color:var(--text);
        }
        .task-observatory-day-title::before{
          content:"";
          width:8px;
          height:8px;
          border-radius:999px;
          background:rgba(47,111,237,0.18);
          box-shadow:0 0 0 4px rgba(47,111,237,0.06);
          flex:0 0 auto;
        }
        .task-observatory-day-meta{
          gap:6px;
        }
        .task-observatory-day-meta .chip{
          background:rgba(255,255,255,0.66);
          border-color:rgba(15,23,42,0.06);
          box-shadow:none;
        }
        .task-observatory-row{
          display:grid;
          gap:6px;
          width:100%;
        }
        .task-observatory-track{
          display:none !important;
          position:relative;
          width:24px;
          flex:0 0 24px;
          justify-content:center;
          padding-top:20px;
        }
        .task-observatory-track::before{
          content:"";
          position:absolute;
          top:0;
          bottom:-22px;
          width:2px;
          background:linear-gradient(180deg, rgba(47,111,237,0.28), rgba(47,111,237,0.04));
        }
        .task-observatory-day:last-child .task-observatory-row:last-child .task-observatory-track::before{
          bottom:18px;
        }
        .task-observatory-track-dot{
          position:relative;
          z-index:1;
          width:14px;
          height:14px;
          border-radius:999px;
          background:#2f6fed;
          border:3px solid rgba(255,255,255,0.96);
          box-shadow:0 0 0 4px rgba(47,111,237,0.12);
        }
        .task-observatory-cards-row{
          display:grid;
          gap:10px;
          align-items:stretch;
          width:100%;
        }
        .task-observatory-card{
          text-align:left;
          border-radius:20px;
          border:1px solid rgba(0,0,0,0.06);
          background:rgba(255,255,255,0.90);
          box-shadow:0 12px 28px rgba(15,23,42,0.04);
          padding:16px;
          display:flex;
          flex-direction:column;
          gap:12px;
          min-height:100%;
          transition:transform 150ms ease, box-shadow 150ms ease, border-color 150ms ease, background 150ms ease;
        }
        .task-observatory-card:hover{
          transform:translateY(-1px);
          box-shadow:0 16px 34px rgba(15,23,42,0.06);
          border-color:rgba(47,111,237,0.18);
        }
        .task-observatory-card.is-parent{
          width:360px;
          background:linear-gradient(180deg, rgba(255,255,255,0.98), rgba(245,249,255,0.92));
          border-color:rgba(47,111,237,0.16);
        }
        .task-observatory-card.is-child{
          width:248px;
          padding:14px;
          gap:10px;
        }
        .task-observatory-card.active{
          border-color:rgba(47,111,237,0.28);
          box-shadow:0 16px 34px rgba(47,111,237,0.12);
        }
        .task-observatory-card-top{
          display:flex;
          align-items:flex-start;
          justify-content:space-between;
          gap:10px;
        }
        .task-observatory-card-title{
          font-size:16px;
          line-height:1.45;
          font-weight:900;
          color:var(--text);
          min-width:0;
        }
        .task-observatory-card-role{
          flex:0 0 auto;
        }
        .task-observatory-card.is-child .task-observatory-card-title{
          font-size:14px;
          font-weight:800;
        }
        .task-observatory-card-note{
          border-radius:16px;
          background:rgba(243,246,252,0.92);
          border:1px solid rgba(0,0,0,0.05);
          padding:10px 12px;
          display:flex;
          flex-direction:column;
          gap:6px;
        }
        .task-observatory-card-note-row{
          font-size:12px;
          line-height:1.65;
          color:var(--muted);
        }
        .task-observatory-card-roles.task-role-groups{
          display:flex;
          align-items:center;
          flex-wrap:wrap;
          gap:8px 12px;
          padding:2px 0;
        }
        .task-observatory-card-roles .task-role-group{
          display:inline-flex;
          align-items:center;
          gap:6px;
          min-width:0;
        }
        .task-observatory-card-roles .task-role-group-label{
          display:inline-flex;
          align-items:center;
          justify-content:center;
          min-width:18px;
          height:18px;
          padding:0 5px;
          border-radius:999px;
          background:rgba(15,23,42,0.06);
          color:var(--muted2);
          font-size:11px;
          font-weight:800;
          flex:0 0 auto;
        }
        .task-observatory-card-roles .task-role-group-avatars{
          display:flex;
          align-items:center;
          gap:4px;
          min-width:0;
        }
        .task-observatory-card-roles .task-role-avatar{
          width:20px;
          height:20px;
          border-radius:999px;
          font-size:10px;
          border-width:1px;
          box-shadow:0 6px 14px rgba(15,23,42,0.08);
          flex:0 0 auto;
        }
        .task-observatory-card-roles .task-role-avatar.assigned{
          font-size:11px;
        }
        .task-observatory-card-note-row strong{
          color:var(--text);
        }
        .task-observatory-load-wrap{
          display:flex;
          justify-content:center;
          padding-top:4px;
        }
        .task-observatory-empty{
          border-radius:16px;
          border:1px dashed rgba(0,0,0,0.10);
          background:rgba(255,255,255,0.76);
          color:var(--muted);
          padding:20px 18px;
          font-size:13px;
          line-height:1.7;
        }
        .task-observatory-range-chip{
          font-weight:700;
        }
        body.panel-task.panel-task-single-canvas .body{
          display:block;
          grid-template-columns:minmax(0,1fr);
          gap:0;
        }
        body.panel-task.panel-task-single-canvas #channelAside,
        body.panel-task.panel-task-single-canvas #convResizeHandle,
        body.panel-task.panel-task-single-canvas .list-header,
        body.panel-task.panel-task-single-canvas #taskMaterialsHeader,
        body.panel-task.panel-task-single-canvas #channelKnowledgeBox{
          display:none !important;
        }
        body.panel-task.panel-task-single-canvas #listView{
          min-width:0;
          width:100%;
          padding:0;
          border:none;
          background:transparent;
          box-shadow:none;
        }
        body.panel-task.panel-task-single-canvas #fileList{
          padding:0;
          overflow:visible;
        }
        body.panel-task.panel-task-single-canvas .task-observatory-page{
          padding:8px 12px 18px;
        }
        body.panel-task.panel-task-single-canvas #detailView{
          display:none !important;
        }
        body.panel-task.panel-task-single-canvas.task-canvas-detail-open #detailView{
          display:none !important;
        }
        body.panel-task.panel-task-single-canvas #detailView .back-to-list{
          display:inline-flex;
        }
        @media (max-width: 900px){
          .task-observatory-head{
            padding:12px 12px 10px;
            gap:10px;
          }
          .task-observatory-head-title{
            font-size:18px;
          }
          .task-observatory-head-meta{
            gap:6px;
          }
          .task-observatory-head-meta-item,
          .task-observatory-head-pill{
            font-size:11px;
          }
          .task-observatory-stat{
            min-width:82px;
            padding:0 10px;
          }
          .task-observatory-refresh-wrap{
            width:100%;
            margin-left:0;
          }
          .task-observatory-refresh-btn{
            width:100%;
          }
          body.panel-task.panel-task-single-canvas #detailView{
            display:none !important;
          }
          .task-observatory-page{
            padding-bottom:16px;
          }
          .task-observatory-canvas{
            min-width:0;
          }
        }
      `;
      document.head.appendChild(style);
    }

    function buildTaskObservatoryStatCard(config = {}) {
      const tag = config.clickable ? "button" : "div";
      const node = el(tag, {
        class: "task-observatory-stat" + (config.clickable ? " is-button" : "") + (config.active ? " is-active" : ""),
        type: config.clickable ? "button" : undefined,
      });
      node.appendChild(el("label", { class: "task-observatory-stat-label", text: String(config.label || "-") }));
      node.appendChild(el("strong", { class: "task-observatory-stat-value", text: String(config.value || "0") }));
      const subText = String(config.sub || "").trim();
      if (subText) node.title = subText;
      if (config.clickable && typeof config.onSelect === "function") {
        node.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          config.onSelect();
        });
      }
      return node;
    }

    function buildTaskObservatoryModeList(listNode, groupsAll, mainMetaNode) {
      const pid = taskObservatoryProjectKey(STATE.project);
      ensureTaskObservatoryStyles();
      const laneFilter = String(STATE.taskLane || "全部").trim() || "全部";
      const specialFilter = taskObservatorySpecialFilter(pid);
      const model = buildTaskObservatoryModel(groupsAll, {
        laneFilter,
        specialFilter,
        visibleLimit: taskObservatoryVisibleLimit(pid),
      });
      if (mainMetaNode) {
        const filterLabel = specialFilter === "blocked" ? "阻塞" : laneFilter;
        mainMetaNode.textContent = "view=任务观察台主视图 · 总任务=" + model.totalGroupCount + " · 当前范围=" + model.visibleGroupCount + " · 筛选=" + filterLabel + " · generated_at=" + DATA.generated_at;
      }

      const page = el("section", { class: "task-observatory-page" });
      const stats = el("section", { class: "task-observatory-stats" });
      const statCards = [
        {
          label: "全部",
          value: model.totalTaskCount,
          sub: "总任务 " + model.totalGroupCount + " 条",
          clickable: true,
          active: laneFilter === "全部" && specialFilter !== "blocked",
          onSelect: () => setTaskObservatoryFilter(pid, "全部"),
        },
        {
          label: "进行中",
          value: model.counts.running,
          sub: "当前主线",
          clickable: true,
          active: laneFilter === "进行中" && specialFilter !== "blocked",
          onSelect: () => setTaskObservatoryFilter(pid, "进行中"),
        },
        {
          label: "待开始",
          value: model.counts.todo,
          sub: "待接续",
          clickable: true,
          active: laneFilter === "待办" && specialFilter !== "blocked",
          onSelect: () => setTaskObservatoryFilter(pid, "待办"),
        },
        {
          label: "待验收",
          value: model.counts.acceptance,
          sub: "即将收口",
          clickable: true,
          active: laneFilter === "待验收" && specialFilter !== "blocked",
          onSelect: () => setTaskObservatoryFilter(pid, "待验收"),
        },
        {
          label: "已完成",
          value: model.counts.done,
          sub: "可回看",
          clickable: true,
          active: laneFilter === "已完成" && specialFilter !== "blocked",
          onSelect: () => setTaskObservatoryFilter(pid, "已完成"),
        },
        {
          label: "阻塞",
          value: model.counts.blocked,
          sub: "需排障",
          clickable: true,
          active: specialFilter === "blocked",
          onSelect: () => setTaskObservatoryFilter(pid, "全部", { special: "blocked" }),
        },
      ];
      statCards.forEach((item) => stats.appendChild(buildTaskObservatoryStatCard(item)));
      if (typeof buildTaskCreateEntryAction === "function") {
        stats.appendChild(buildTaskCreateEntryAction(pid));
      }
      stats.appendChild(buildTaskObservatoryRefreshAction(pid));
      page.appendChild(stats);

      const board = el("section", { class: "task-observatory-board" });
      if (!model.visibleGroups.length) {
        board.appendChild(el("div", {
          class: "task-observatory-empty",
          text: "当前筛选下没有可展示的总任务主线。可以切回“全部”继续查看。",
        }));
      } else {
        const scroll = el("div", { class: "task-observatory-scroll" });
        const canvas = el("div", { class: "task-observatory-canvas" });
        model.days.forEach((day) => {
          const dayNode = el("section", { class: "task-observatory-day" });
          const dayHead = el("div", { class: "task-observatory-day-head" });
          dayHead.appendChild(el("div", { class: "task-observatory-day-title", text: day.label }));
          const dayMeta = el("div", { class: "task-observatory-day-meta" });
          const dayMasterTotal = day.items.length;
          const dayChildTotal = day.items.reduce((sum, group) => sum + Math.max(0, Number(group && group.childTotal || 0)), 0);
          dayMeta.appendChild(chip("主任务 " + dayMasterTotal, "muted"));
          dayMeta.appendChild(chip("子任务 " + dayChildTotal, "muted"));
          dayNode.appendChild(dayHead);
          dayHead.appendChild(dayMeta);

          day.items.forEach((group) => {
            const master = group && group.master ? group.master : null;
            if (!master) return;
            const masterPath = String(master.path || "");
            const masterTaskId = taskStableIdOfItem(master);
            const children = Array.isArray(group.children) ? group.children : [];
            const selectedPath = String(STATE.selectedPath || "");
            const selectedTaskId = normalizeTaskStableId(STATE.selectedTaskId || "");
            const hasChildSelected = children.some((child) => taskSelectionMatchesItem(child, selectedPath, selectedTaskId));
            const row = el("div", { class: "task-observatory-row" });
            const track = el("div", { class: "task-observatory-track" });
            track.appendChild(el("span", { class: "task-observatory-track-dot" }));
            row.appendChild(track);
            const cards = el("div", { class: "task-observatory-cards-row" });

            const masterFlags = taskStatusFlags(master);
            const parentMetaItems = [
              ["子任务 " + children.length, "muted"],
              ["链路 " + Number(group.total || (children.length + 1)) + " 项", "muted"],
            ];
            if (masterFlags.supervised) parentMetaItems.push(["关注", "bad"]);
            if (masterFlags.blocked) parentMetaItems.push(["阻塞", "bad"]);
            const pushBtn = createTaskPushEntryBtn(master, true);
            const parentCard = buildUnifiedTaskListCard({
              ...master,
              task_primary_status: group.masterBucket || master.task_primary_status || master.status,
              latest_action_text: taskGroupSummaryText(group, children),
              latest_action_at: group.latestAt || master.updated_at,
            }, {
              source: "task-home",
              projectId: STATE.project,
              channelName: resolveTaskGroupChannel(group),
              forceTaskType: "parent",
              active: taskSelectionMatchesItem(master, selectedPath, selectedTaskId) || hasChildSelected,
              metaItems: parentMetaItems,
              actions: pushBtn ? [pushBtn] : [],
              onOpen: () => setSelectedTaskRef(masterPath, masterTaskId, { openUnifiedDetail: true, forceTaskType: "parent" }),
            });
            cards.appendChild(parentCard);

            if (children.length) {
              cards.appendChild(buildUnifiedTaskChildGrid(children, (child) => buildUnifiedTaskListCard(child, {
                source: "task-home-child",
                projectId: STATE.project,
                channelName: child && child.channel,
                forceTaskType: "child",
                active: taskSelectionMatchesItem(child, selectedPath, selectedTaskId),
                latestText: "当前状态：" + bucketKeyForStatus(child && child.status),
                onOpen: () => setSelectedTaskRef(child && child.path, taskStableIdOfItem(child), { openUnifiedDetail: true, forceTaskType: "child" }),
              })));
            }

            row.appendChild(cards);
            dayNode.appendChild(row);
          });

          canvas.appendChild(dayNode);
        });
        scroll.appendChild(canvas);
        board.appendChild(scroll);
        if (model.hasMore) {
          const loadWrap = el("div", { class: "task-observatory-load-wrap" });
          const loadBtn = el("button", {
            class: "btn task-observatory-range-chip",
            type: "button",
            text: "加载更早任务（已载入 " + model.visibleGroupCount + "/" + model.filteredGroupCount + "）",
          });
          loadBtn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            increaseTaskObservatoryVisibleLimit(pid);
            render();
          });
          loadWrap.appendChild(loadBtn);
          board.appendChild(loadWrap);
        }
      }

      page.appendChild(board);
      listNode.appendChild(page);
    }

    function buildOrgBoardLayout(nodes, width, height) {
      const rows = Array.isArray(nodes) ? nodes : [];
      if (!rows.length) return [];
      const withPos = rows.filter((r) => Number.isFinite(Number(r && r.x)) && Number.isFinite(Number(r && r.y)));
      const minPaddingX = 36;
      const minPaddingY = 30;
      const w = Math.max(320, Number(width) || 920);
      const h = Math.max(220, Number(height) || 520);
      if (!withPos.length) {
        const cols = Math.max(2, Math.ceil(Math.sqrt(rows.length)));
        return rows.map((row, idx) => {
          const c = idx % cols;
          const r = Math.floor(idx / cols);
          const cx = minPaddingX + ((w - minPaddingX * 2) * ((c + 0.5) / cols));
          const cy = minPaddingY + ((h - minPaddingY * 2) * ((r + 0.5) / Math.max(1, Math.ceil(rows.length / cols))));
          return { row, x: cx, y: cy };
        });
      }
      let minX = Number.POSITIVE_INFINITY;
      let maxX = Number.NEGATIVE_INFINITY;
      let minY = Number.POSITIVE_INFINITY;
      let maxY = Number.NEGATIVE_INFINITY;
      withPos.forEach((row) => {
        const x = Number(row.x);
        const y = Number(row.y);
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      });
      const spanX = Math.max(1, maxX - minX);
      const spanY = Math.max(1, maxY - minY);
      return rows.map((row, idx) => {
        const xRaw = Number.isFinite(Number(row && row.x)) ? Number(row.x) : (minX + (idx % 6) * 120);
        const yRaw = Number.isFinite(Number(row && row.y)) ? Number(row.y) : (minY + Math.floor(idx / 6) * 80);
        const nx = (xRaw - minX) / spanX;
        const ny = (yRaw - minY) / spanY;
        const x = minPaddingX + nx * (w - minPaddingX * 2);
        const y = minPaddingY + ny * (h - minPaddingY * 2);
        return { row, x, y };
      });
    }

    async function fetchOrgBoardData(projectId, opts = {}) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return null;
      const force = !!opts.force;
      const maxAgeMs = Number.isFinite(Number(opts.maxAgeMs)) ? Math.max(0, Number(opts.maxAgeMs)) : 12000;
      const cached = orgBoardCache(pid);
      const fresh = cached && !force && ((Date.now() - Number(cached.fetchedAtMs || 0)) < maxAgeMs);
      if (fresh) return cached;
      const retryAfterMs = Number(ORG_BOARD_UI.retryAfterByProject[pid] || 0);
      if (!force && retryAfterMs > Date.now()) return cached;
      if (ORG_BOARD_UI.loadingByProject[pid]) return cached;

      ORG_BOARD_UI.loadingByProject[pid] = true;
      ORG_BOARD_UI.errorByProject[pid] = "";
      ORG_BOARD_UI.noteByProject[pid] = "";
      const seq = Number(ORG_BOARD_UI.seqByProject[pid] || 0) + 1;
      ORG_BOARD_UI.seqByProject[pid] = seq;
      try {
        const graphUrl = "/api/board/global-resource-graph?project_id=" + encodeURIComponent(pid) + "&run_limit=600";
        const runtimeUrl = "/api/projects/" + encodeURIComponent(pid) + "/runtime-bubbles?limit=120&bubble_limit=120";
        const [graphResp, runtimeResp] = await Promise.all([
          fetch(graphUrl, { method: "GET", headers: authHeaders({ Accept: "application/json" }), cache: "no-store" }),
          fetch(runtimeUrl, { method: "GET", headers: authHeaders({ Accept: "application/json" }), cache: "no-store" }),
        ]);
        if (!graphResp.ok) {
          const detail = await parseResponseDetail(graphResp);
          throw new Error(detail || ("组织快照加载失败（HTTP " + graphResp.status + "）"));
        }
        if (!runtimeResp.ok) {
          const detail = await parseResponseDetail(runtimeResp);
          throw new Error(detail || ("运行态关系加载失败（HTTP " + runtimeResp.status + "）"));
        }
        const graph = await graphResp.json().catch(() => ({}));
        const runtime = await runtimeResp.json().catch(() => ({}));
        if (Number(ORG_BOARD_UI.seqByProject[pid] || 0) === seq) {
          ORG_BOARD_UI.cacheByProject[pid] = {
            graph: (graph && typeof graph === "object") ? graph : {},
            runtime: (runtime && typeof runtime === "object") ? runtime : {},
            fetchedAt: new Date().toISOString(),
            fetchedAtMs: Date.now(),
          };
          ORG_BOARD_UI.errorByProject[pid] = "";
          ORG_BOARD_UI.noteByProject[pid] = "";
          ORG_BOARD_UI.retryAfterByProject[pid] = 0;
        }
      } catch (e) {
        if (Number(ORG_BOARD_UI.seqByProject[pid] || 0) === seq) {
          const msg = String((e && e.message) || e || "组织快照加载失败");
          ORG_BOARD_UI.errorByProject[pid] = msg;
          ORG_BOARD_UI.retryAfterByProject[pid] = Date.now() + 8000;
          if (!cached) {
            ORG_BOARD_UI.cacheByProject[pid] = {
              graph: {},
              runtime: {},
              fetchedAt: new Date().toISOString(),
              fetchedAtMs: Date.now(),
            };
          }
        }
      } finally {
        if (Number(ORG_BOARD_UI.seqByProject[pid] || 0) === seq) {
          ORG_BOARD_UI.loadingByProject[pid] = false;
        }
      }
      return orgBoardCache(pid);
    }

    function openProjectOrg3D(projectId) {
      const pid = String(projectId || "").trim();
      const base = String(OVERVIEW_PAGE || "/share/project-overview-dashboard.html").trim();
      if (!pid) {
        openNew(base);
        return;
      }
      try {
        // 关键修复：相对路径需要基于当前页面路径解析（/dist 或 /share），
        // 不能基于 origin，否则会被解析到站点根目录并触发 404。
        const u = new URL(base, location.href);
        const hash = new URLSearchParams(String(u.hash || "").replace(/^#/, ""));
        hash.set("p", pid);
        u.hash = hash.toString();
        openNew(u.toString());
      } catch (_) {
        const sep = base.includes("#") ? "&" : "#";
        openNew(base + sep + "p=" + encodeURIComponent(pid));
      }
    }

    async function fetchProjectScheduleQueue(projectId, opts = {}) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return null;
      const force = !!opts.force;
      const maxAgeMs = Number.isFinite(Number(opts.maxAgeMs)) ? Math.max(0, Number(opts.maxAgeMs)) : 6000;
      const cached = projectScheduleCache(pid);
      const fresh = cached && !force && ((Date.now() - Number(cached.fetchedAtMs || 0)) < maxAgeMs);
      if (fresh) return cached.queue || null;
      const retryAfterMs = Number(PROJECT_SCHEDULE_UI.retryAfterByProject[pid] || 0);
      if (!force && retryAfterMs > Date.now()) return cached ? (cached.queue || null) : null;
      if (PROJECT_SCHEDULE_UI.loadingByProject[pid]) return cached ? (cached.queue || null) : null;

      PROJECT_SCHEDULE_UI.loadingByProject[pid] = true;
      PROJECT_SCHEDULE_UI.errorByProject[pid] = "";
      const seq = Number(PROJECT_SCHEDULE_UI.seqByProject[pid] || 0) + 1;
      PROJECT_SCHEDULE_UI.seqByProject[pid] = seq;
      try {
        const resp = await fetch("/api/projects/" + encodeURIComponent(pid) + "/schedule-queue", {
          method: "GET",
          headers: authHeaders({ Accept: "application/json" }),
          cache: "no-store",
        });
        if (!resp.ok) {
          const detail = await parseResponseDetail(resp);
          throw new Error(detail || ("HTTP " + resp.status));
        }
        const data = await resp.json();
        if (Number(PROJECT_SCHEDULE_UI.seqByProject[pid] || 0) === seq) {
          PROJECT_SCHEDULE_UI.cacheByProject[pid] = {
            queue: data && typeof data === "object" ? data : {},
            fetchedAt: new Date().toISOString(),
            fetchedAtMs: Date.now(),
          };
          PROJECT_SCHEDULE_UI.errorByProject[pid] = "";
          PROJECT_SCHEDULE_UI.retryAfterByProject[pid] = 0;
          PROJECT_SCHEDULE_UI.noteByProject[pid] = "";
        }
      } catch (e) {
        if (Number(PROJECT_SCHEDULE_UI.seqByProject[pid] || 0) === seq) {
          const msg = e && e.message ? String(e.message) : "排期队列加载失败";
          PROJECT_SCHEDULE_UI.errorByProject[pid] = msg;
          const is404 = /(^|\s)404(\s|$)/.test(msg) || /not found/i.test(msg);
          const nowMs = Date.now();
          PROJECT_SCHEDULE_UI.retryAfterByProject[pid] = nowMs + (is404 ? 30000 : 8000);
          // 失败后写入一次抓取时间，避免在连续 render 周期内反复请求导致 UI 抖动。
          const keepQueue = cached && cached.queue && typeof cached.queue === "object" ? cached.queue : {};
          PROJECT_SCHEDULE_UI.cacheByProject[pid] = {
            queue: keepQueue,
            fetchedAt: new Date(nowMs).toISOString(),
            fetchedAtMs: nowMs,
          };
          if (is404) {
            PROJECT_SCHEDULE_UI.noteByProject[pid] = "当前运行服务未启用排期接口，已降级为任务模式可用。";
          }
        }
      } finally {
        if (Number(PROJECT_SCHEDULE_UI.seqByProject[pid] || 0) === seq) {
          PROJECT_SCHEDULE_UI.loadingByProject[pid] = false;
        }
      }
      const updated = projectScheduleCache(pid);
      return updated ? (updated.queue || null) : null;
    }

    async function saveProjectScheduleQueue(projectId, taskPaths, noteText) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") return null;
      if (PROJECT_SCHEDULE_UI.savingByProject[pid]) return null;
      const paths = Array.isArray(taskPaths)
        ? Array.from(new Set(taskPaths.map((x) => normalizeScheduleTaskPathForProject(pid, x)).filter(Boolean)))
        : [];
      PROJECT_SCHEDULE_UI.savingByProject[pid] = true;
      PROJECT_SCHEDULE_UI.errorByProject[pid] = "";
      PROJECT_SCHEDULE_UI.noteByProject[pid] = "";
      render();
      try {
        const resp = await fetch("/api/projects/" + encodeURIComponent(pid) + "/schedule-queue", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ action: "replace", task_paths: paths }),
        });
        if (!resp.ok) {
          const detail = await parseResponseDetail(resp);
          throw new Error(detail || ("HTTP " + resp.status));
        }
        const data = await resp.json().catch(() => ({}));
        const queue = data && data.queue && typeof data.queue === "object" ? data.queue : {};
        PROJECT_SCHEDULE_UI.cacheByProject[pid] = {
          queue,
          fetchedAt: new Date().toISOString(),
          fetchedAtMs: Date.now(),
        };
        PROJECT_SCHEDULE_UI.errorByProject[pid] = "";
        PROJECT_SCHEDULE_UI.noteByProject[pid] = noteText || "排期队列已保存。";
      } catch (e) {
        PROJECT_SCHEDULE_UI.errorByProject[pid] = e && e.message ? String(e.message) : "排期队列保存失败";
      } finally {
        PROJECT_SCHEDULE_UI.savingByProject[pid] = false;
        render();
      }
      const cached = projectScheduleCache(pid);
      return cached ? (cached.queue || null) : null;
    }

    async function mutateProjectScheduleQueue(projectId, action, taskPath, noteText) {
      const pid = String(projectId || "").trim();
      const path = normalizeScheduleTaskPathForProject(pid, taskPath);
      const act = String(action || "").trim().toLowerCase();
      if (!pid || pid === "overview" || !path) return null;
      if (PROJECT_SCHEDULE_UI.savingByProject[pid]) return null;
      PROJECT_SCHEDULE_UI.savingByProject[pid] = true;
      PROJECT_SCHEDULE_UI.errorByProject[pid] = "";
      PROJECT_SCHEDULE_UI.noteByProject[pid] = "";
      render();
      try {
        const resp = await fetch("/api/projects/" + encodeURIComponent(pid) + "/schedule-queue", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ action: act, task_path: path }),
        });
        if (!resp.ok) {
          const detail = await parseResponseDetail(resp);
          throw new Error(detail || ("HTTP " + resp.status));
        }
        const data = await resp.json().catch(() => ({}));
        const queue = data && data.queue && typeof data.queue === "object" ? data.queue : {};
        PROJECT_SCHEDULE_UI.cacheByProject[pid] = {
          queue,
          fetchedAt: new Date().toISOString(),
          fetchedAtMs: Date.now(),
        };
        PROJECT_SCHEDULE_UI.errorByProject[pid] = "";
        PROJECT_SCHEDULE_UI.noteByProject[pid] = String(noteText || "").trim() || "排期队列已更新。";
      } catch (e) {
        PROJECT_SCHEDULE_UI.errorByProject[pid] = e && e.message ? String(e.message) : "排期队列更新失败";
      } finally {
        PROJECT_SCHEDULE_UI.savingByProject[pid] = false;
        render();
      }
      const cached = projectScheduleCache(pid);
      return cached ? (cached.queue || null) : null;
    }

    async function setTaskScheduleState(projectId, taskPath, shouldSchedule, source = "manual") {
      const pid = String(projectId || "").trim();
      const path = normalizeScheduleTaskPathForProject(pid, taskPath);
      if (!pid || pid === "overview" || !path) return false;
      const nowScheduled = isTaskInProjectSchedule(pid, path);
      const targetScheduled = !!shouldSchedule;
      if (nowScheduled === targetScheduled) {
        PROJECT_SCHEDULE_UI.noteByProject[pid] = targetScheduled ? "任务已在排期队列中。" : "任务当前未排期。";
        render();
        return true;
      }
      const action = targetScheduled ? "add" : "remove";
      const sourceText = source === "drag" ? "（拖拽）" : "";
      const note = targetScheduled ? ("已加入排期" + sourceText + "。") : ("已取消排期" + sourceText + "。");
      await mutateProjectScheduleQueue(pid, action, path, note);
      return !PROJECT_SCHEDULE_UI.errorByProject[pid];
    }

    function toggleTaskLaneCollapse(lane) {
      if (!(lane in STATE.taskLaneCollapsed)) return;
      STATE.taskLaneCollapsed[lane] = !STATE.taskLaneCollapsed[lane];
      render();
    }

    function toggleTaskGroupExpanded(key) {
      const k = String(key || "").trim();
      if (!k) return;
      STATE.taskGroupExpanded[k] = !STATE.taskGroupExpanded[k];
      render();
    }

    function normalizeTaskGroupSource(raw) {
      const v = String(raw || "").trim().toLowerCase();
      if (v === "active" || v === "done" || v === "all") return v;
      return "active";
    }

    function isTaskBucketActive(bucket) {
      return bucket === "待办"
        || bucket === "进行中"
        || bucket === "待验收";
    }

    function taskChildMatchesSource(child, source) {
      const b = taskPrimaryStatus(child);
      const mode = normalizeTaskGroupSource(source);
      if (mode === "all") return true;
      if (mode === "done") return b === "已完成";
      return isTaskBucketActive(b);
    }

    function taskGroupSummaryText(group, childrenView) {
      const children = Array.isArray(childrenView)
        ? childrenView
        : (Array.isArray(group && group.children) ? group.children : []);
      if (!children.length) return "未拆分子任务";
      const top = children.slice(0, 3).map((x) => shortTitle(x.title || ""));
      const more = children.length > 3 ? (" 等" + children.length + "项") : "";
      return "任务划分：" + top.join("、") + more;
    }

    function resolveTaskGroupChannel(group) {
      const g = group || {};
      const master = g.master || null;
      const mc = String((master && master.channel) || "").trim();
      if (mc) return mc;
      const children = Array.isArray(g.children) ? g.children : [];
      const hit = children.find((c) => String((c && c.channel) || "").trim());
      return String((hit && hit.channel) || "").trim() || "未归类";
    }

    function buildScheduleModeList(listNode, groupsAll, laneFilter, mainMetaNode) {
      STATE.taskModule = "tasks";
      buildTaskObservatoryModeList(listNode, groupsAll, mainMetaNode);
    }

    function buildOrgModeList(listNode, mainMetaNode, opts) {
      const viewMode = String((opts && opts.view) || STATE.panelMode || "org").trim().toLowerCase();
      const isOrgView = viewMode === "org";
      const allowManualEditing = !isOrgView;
      const pid = String(STATE.project || "").trim();
      const cache = orgBoardCache(pid);
      const snapshot = orgBoardSnapshot(pid);
      const runtime = orgBoardRuntime(pid);
      const graphRaw = cache && cache.graph && typeof cache.graph === "object" ? cache.graph : {};
      const graphNodes = Array.isArray(graphRaw.nodes) ? graphRaw.nodes : [];
      const graphIndex = graphRaw && graphRaw.index && typeof graphRaw.index === "object" ? graphRaw.index : {};
      const nodes = Array.isArray(snapshot.nodes) ? snapshot.nodes : [];
      const edges = Array.isArray(snapshot.edges) ? snapshot.edges : [];
      const relationRows = Array.isArray(runtime.runtime_relations) ? runtime.runtime_relations : [];
      const graphAgentNodeBySession = new Map();
      graphNodes.forEach((row) => {
        if (!row || String(row.type || "").trim() !== "agent") return;
        const sid = String(row.session_id || "").trim();
        if (!sid) return;
        graphAgentNodeBySession.set(sid, row);
      });
      const channelSessionByName = new Map();
      nodes.forEach((row) => {
        if (orgNodeType(row) !== "channel") return;
        const channelName = String(((row && row.meta && row.meta.channel_name) || row.label || "")).trim();
        if (!channelName) return;
        const sid = String(((row && row.meta && row.meta.session_id) || row.session_id || "")).trim();
        if (sid) channelSessionByName.set(channelName, sid);
      });
      const allAgentNodes = nodes.filter((row) => orgNodeType(row) === "agent");
      const allAgentIdSet = new Set(
        allAgentNodes
          .map((row) => String((row && row.agent_id) || "").trim())
          .filter((x) => !!x),
      );
      const agentLookup = buildOrgAgentLookup(nodes);
      const relations = relationRows.filter((rel) => {
        const src = resolveRuntimeAgentId(nodes, rel, "source", agentLookup);
        const dst = resolveRuntimeAgentId(nodes, rel, "target", agentLookup);
        return allAgentIdSet.has(src) && allAgentIdSet.has(dst);
      });
      const activeRelations = relations.filter(relationIsActive);
      const relationHotByAgent = new Map();
      activeRelations.forEach((rel) => {
        const src = resolveRuntimeAgentId(nodes, rel, "source", agentLookup);
        const dst = resolveRuntimeAgentId(nodes, rel, "target", agentLookup);
        if (src) relationHotByAgent.set(src, Number(relationHotByAgent.get(src) || 0) + 1);
        if (dst) relationHotByAgent.set(dst, Number(relationHotByAgent.get(dst) || 0) + 1);
      });
      const classifyAgentState = (row) => {
        const aid = String((row && row.agent_id) || "").trim();
        const channelName = String(((row && row.meta && row.meta.channel_name) || "")).trim();
        const currentSid = channelSessionByName.get(channelName) || "";
        const stateRaw = String(((row && row.meta && row.meta.agent_state) || row.agent_state || "")).trim().toLowerCase();
        const hot = Number(relationHotByAgent.get(aid) || 0);
        if (hot > 0 || stateRaw === "active" || stateRaw === "running") return "active";
        if (currentSid && aid && aid !== currentSid) return "legacy";
        return "idle";
      };
      const stateCount = { active: 0, idle: 0, legacy: 0 };
      allAgentNodes.forEach((row) => {
        const cat = classifyAgentState(row);
        if (cat === "active" || cat === "idle" || cat === "legacy") stateCount[cat] += 1;
      });
      const filterMap = ORG_BOARD_UI.agentFilterByProject || (ORG_BOARD_UI.agentFilterByProject = Object.create(null));
      const AGENT_FILTER_KEYS = ["active", "idle", "legacy"];
      const normalizeAgentFilterSelection = (raw) => {
        const out = new Set();
        if (Array.isArray(raw)) {
          raw.forEach((v) => {
            const key = String(v || "").trim();
            if (AGENT_FILTER_KEYS.includes(key)) out.add(key);
          });
        } else if (raw && typeof raw === "object") {
          AGENT_FILTER_KEYS.forEach((key) => {
            if (raw[key]) out.add(key);
          });
        } else {
          const text = String(raw || "").trim();
          if (text && text !== "all") {
            text.split(",").forEach((piece) => {
              const key = String(piece || "").trim();
              if (AGENT_FILTER_KEYS.includes(key)) out.add(key);
            });
          }
        }
        if (!out.size) AGENT_FILTER_KEYS.forEach((k) => out.add(k));
        return out;
      };
      const persistAgentFilterSelection = (set) => {
        const next = Array.from(set || []).filter((key) => AGENT_FILTER_KEYS.includes(String(key || "").trim()));
        if (!next.length || next.length === AGENT_FILTER_KEYS.length) {
          filterMap[pid] = "all";
          return;
        }
        filterMap[pid] = next;
      };
      const selectedAgentStates = normalizeAgentFilterSelection(filterMap[pid]);
      const REL_MATTER_KEYS = ["dispatch", "inspection", "callback", "recovery", "manual", "other"];
      const REL_MATTER_LABEL = {
        dispatch: "派发",
        inspection: "巡查",
        callback: "回执",
        recovery: "恢复",
        manual: "人工",
        other: "其他",
      };
      const REL_MATTER_OFFSET_Y = {
        dispatch: -7,
        inspection: -3,
        callback: 1,
        recovery: 5,
        manual: 9,
        other: 13,
      };
      const classifyRelationMatter = (rel) => {
        const reason = String((rel && rel.reason) || "").trim().toLowerCase();
        const triggerType = String((rel && rel.trigger_type) || (rel && rel.triggerType) || "").trim().toLowerCase();
        const messageKind = String((rel && rel.message_kind) || (rel && rel.messageKind) || "").trim().toLowerCase();
        const bag = [reason, triggerType, messageKind].join(" ");
        if (!bag) return "other";
        if (bag.includes("recovery") || bag.includes("restart") || bag.includes("恢复") || bag.includes("重启")) return "recovery";
        if (bag.includes("inspection") || bag.includes("reminder") || bag.includes("巡查") || bag.includes("督办")) return "inspection";
        if (bag.includes("callback") || bag.includes("回执") || bag.includes("收口")) return "callback";
        if (bag.includes("manual") || bag.includes("人工") || bag.includes("手动")) return "manual";
        if (bag.includes("dispatch") || bag.includes("announce") || bag.includes("派发") || bag.includes("推送")) return "dispatch";
        return "other";
      };
      const matterFilterMap = ORG_BOARD_UI.relationMatterFilterByProject || (ORG_BOARD_UI.relationMatterFilterByProject = Object.create(null));
      const normalizeMatterSelection = (raw) => {
        const out = new Set();
        if (Array.isArray(raw)) {
          raw.forEach((v) => {
            const key = String(v || "").trim();
            if (REL_MATTER_KEYS.includes(key)) out.add(key);
          });
        } else {
          const text = String(raw || "").trim();
          if (text && text !== "all") {
            text.split(",").forEach((v) => {
              const key = String(v || "").trim();
              if (REL_MATTER_KEYS.includes(key)) out.add(key);
            });
          }
        }
        if (!out.size) REL_MATTER_KEYS.forEach((k) => out.add(k));
        return out;
      };
      const persistMatterSelection = (set) => {
        const next = Array.from(set || []).filter((key) => REL_MATTER_KEYS.includes(String(key || "").trim()));
        if (!next.length || next.length === REL_MATTER_KEYS.length) {
          matterFilterMap[pid] = "all";
          return;
        }
        matterFilterMap[pid] = next;
      };
      const selectedMatterTypes = normalizeMatterSelection(matterFilterMap[pid]);
      const relFilter = selectedMatterTypes;
      const manualStore = orgProjectRelationStore(pid, true) || { types: [], relations: [] };
      const manualTypes = normalizeOrgRelationTypes(manualStore.types).filter((it) => it && it.enabled !== false);
      const manualTypeById = new Map();
      manualTypes.forEach((it) => {
        const id = String((it && it.id) || "").trim();
        if (!id) return;
        manualTypeById.set(id, it);
      });
      const manualRelationsAll = normalizeOrgManualRelations(manualStore.relations).filter((rel) => {
        const tid = String((rel && rel.relation_type_id) || "").trim();
        const src = String((rel && rel.source_agent_id) || "").trim();
        const dst = String((rel && rel.target_agent_id) || "").trim();
        return !!tid && !!src && !!dst && manualTypeById.has(tid) && allAgentIdSet.has(src) && allAgentIdSet.has(dst);
      });
      const manualFilterMap = ORG_BOARD_UI.manualTypeFilterByProject || (ORG_BOARD_UI.manualTypeFilterByProject = Object.create(null));
      const manualTypeIds = manualTypes.map((it) => String((it && it.id) || "").trim()).filter(Boolean);
      const normalizeManualTypeSelection = (raw) => {
        const out = new Set();
        if (Array.isArray(raw)) {
          raw.forEach((v) => {
            const key = String(v || "").trim();
            if (manualTypeIds.includes(key)) out.add(key);
          });
        } else {
          const text = String(raw || "").trim();
          if (text && text !== "all") {
            text.split(",").forEach((v) => {
              const key = String(v || "").trim();
              if (manualTypeIds.includes(key)) out.add(key);
            });
          }
        }
        if (!out.size) manualTypeIds.forEach((id) => out.add(id));
        return out;
      };
      const persistManualTypeSelection = (set) => {
        const next = Array.from(set || []).filter((id) => manualTypeIds.includes(String(id || "").trim()));
        if (!next.length || next.length === manualTypeIds.length) {
          manualFilterMap[pid] = "all";
          return;
        }
        manualFilterMap[pid] = next;
      };
      const selectedManualTypes = normalizeManualTypeSelection(manualFilterMap[pid]);
      const visibleNodes = nodes.filter((row) => {
        if (orgNodeType(row) !== "agent") return true;
        return selectedAgentStates.has(classifyAgentState(row));
      });
      const visibleAgentIdSet = new Set(
        visibleNodes
          .filter((row) => orgNodeType(row) === "agent")
          .map((row) => String((row && row.agent_id) || "").trim())
          .filter((x) => !!x),
      );
      const selectedAgentMap = ORG_BOARD_UI.selectedAgentByProject || (ORG_BOARD_UI.selectedAgentByProject = Object.create(null));
      let selectedAgentId = String(selectedAgentMap[pid] || "").trim();
      if (selectedAgentId && !visibleAgentIdSet.has(selectedAgentId)) {
        selectedAgentId = "";
        selectedAgentMap[pid] = "";
      }
      const linkDraftMap = ORG_BOARD_UI.linkDraftByProject || (ORG_BOARD_UI.linkDraftByProject = Object.create(null));
      const linkEditorMap = ORG_BOARD_UI.linkEditorByProject || (ORG_BOARD_UI.linkEditorByProject = Object.create(null));
      const rawLinkDraft = linkDraftMap[pid] && typeof linkDraftMap[pid] === "object" ? linkDraftMap[pid] : null;
      const linkDraft = rawLinkDraft && visibleAgentIdSet.has(String(rawLinkDraft.source_agent_id || "").trim())
        ? rawLinkDraft
        : null;
      if (!linkDraft && rawLinkDraft) delete linkDraftMap[pid];
      const rawLinkEditor = linkEditorMap[pid] && typeof linkEditorMap[pid] === "object" ? linkEditorMap[pid] : null;
      const linkEditor = rawLinkEditor
        && visibleAgentIdSet.has(String(rawLinkEditor.source_agent_id || "").trim())
        && visibleAgentIdSet.has(String(rawLinkEditor.target_agent_id || "").trim())
        ? rawLinkEditor
        : null;
      if (!linkEditor && rawLinkEditor) delete linkEditorMap[pid];
      if (!allowManualEditing) {
        if (rawLinkDraft) delete linkDraftMap[pid];
        if (rawLinkEditor) delete linkEditorMap[pid];
      }
      const visibleRelationsRaw = relations.filter((rel) => {
        const src = resolveRuntimeAgentId(nodes, rel, "source", agentLookup);
        const dst = resolveRuntimeAgentId(nodes, rel, "target", agentLookup);
        return visibleAgentIdSet.has(src) && visibleAgentIdSet.has(dst);
      });
      const visibleManualRelationsRaw = manualRelationsAll.filter((rel) => {
        const src = String((rel && rel.source_agent_id) || "").trim();
        const dst = String((rel && rel.target_agent_id) || "").trim();
        return visibleAgentIdSet.has(src) && visibleAgentIdSet.has(dst);
      });
      const matterCountByType = Object.create(null);
      REL_MATTER_KEYS.forEach((k) => { matterCountByType[k] = 0; });
      visibleRelationsRaw.forEach((rel) => {
        const matter = classifyRelationMatter(rel);
        matterCountByType[matter] = Number(matterCountByType[matter] || 0) + 1;
      });
      const manualCountByType = Object.create(null);
      manualTypeIds.forEach((id) => { manualCountByType[id] = 0; });
      visibleManualRelationsRaw.forEach((rel) => {
        const typeId = String((rel && rel.relation_type_id) || "").trim();
        if (!typeId) return;
        manualCountByType[typeId] = Number(manualCountByType[typeId] || 0) + 1;
      });
      const visibleActiveRelations = activeRelations.filter((rel) => {
        const src = resolveRuntimeAgentId(nodes, rel, "source", agentLookup);
        const dst = resolveRuntimeAgentId(nodes, rel, "target", agentLookup);
        return visibleAgentIdSet.has(src) && visibleAgentIdSet.has(dst);
      });
      const visibleRelations = isOrgView
        ? visibleActiveRelations
        : visibleRelationsRaw.filter((rel) => relFilter.has(classifyRelationMatter(rel)));
      const visibleManualRelations = allowManualEditing
        ? visibleManualRelationsRaw.filter((rel) => selectedManualTypes.has(String((rel && rel.relation_type_id) || "").trim()))
        : [];
      if (isOrgView) {
        const agentStateLabelLocal = (st) => {
          const key = String(st || "").trim();
          if (key === "active") return "活跃";
          if (key === "legacy") return "废弃";
          return "空闲";
        };
        const agentStateToneLocal = (st) => {
          const key = String(st || "").trim();
          if (key === "active") return "good";
          if (key === "legacy") return "warn";
          return "muted";
        };
        const channelNodeLabel = (row) => {
          return String(((row && row.meta && row.meta.channel_name) || row.label || "未命名通道")).trim() || "未命名通道";
        };
        const agentRows = visibleNodes.filter((row) => orgNodeType(row) === "agent");
        const channelRows = visibleNodes.filter((row) => orgNodeType(row) === "channel");
        const agentById = new Map();
        agentRows.forEach((row) => {
          const aid = String((row && row.agent_id) || "").trim();
          if (aid) agentById.set(aid, row);
        });
        const agentChildrenByNodeId = new Map();
        agentRows.forEach((row) => {
          const parentId = String((row && row.parent_node_id) || "").trim();
          if (!parentId) return;
          if (!agentChildrenByNodeId.has(parentId)) agentChildrenByNodeId.set(parentId, []);
          agentChildrenByNodeId.get(parentId).push(row);
        });
        const channelBlocks = channelRows.map((row) => {
          const nodeId = String((row && row.node_id) || "").trim();
          const children = (agentChildrenByNodeId.get(nodeId) || []).slice().sort((a, b) => {
            const ah = Number(relationHotByAgent.get(String((a && a.agent_id) || "").trim()) || 0);
            const bh = Number(relationHotByAgent.get(String((b && b.agent_id) || "").trim()) || 0);
            if (ah !== bh) return bh - ah;
            return normalizeOrgNodeLabel(a).localeCompare(normalizeOrgNodeLabel(b), "zh-Hans-CN");
          });
          return { row, children };
        }).sort((a, b) => channelNodeLabel(a.row).localeCompare(channelNodeLabel(b.row), "zh-Hans-CN"));
        const fallbackSelected = agentRows.find((row) => classifyAgentState(row) === "active")
          || agentRows[0]
          || channelRows[0]
          || visibleNodes[0]
          || null;
        const fallbackSelectedId = String((fallbackSelected && (fallbackSelected.agent_id || fallbackSelected.node_id)) || "").trim();
        if (!selectedAgentId && fallbackSelected && orgNodeType(fallbackSelected) === "agent") {
          selectedAgentId = fallbackSelectedId;
          selectedAgentMap[pid] = fallbackSelectedId;
        }
        const selectedEntity = (selectedAgentId && agentById.get(selectedAgentId)) || fallbackSelected || null;
        const selectedEntityType = orgNodeType(selectedEntity);
        const selectedEntityLabel = selectedEntity ? normalizeOrgNodeLabel(selectedEntity) : "未选择节点";
        const relatedRuntime = visibleRelations
          .filter((rel) => {
            if (!selectedAgentId || selectedEntityType !== "agent") return true;
            const src = resolveRuntimeAgentId(nodes, rel, "source", agentLookup);
            const dst = resolveRuntimeAgentId(nodes, rel, "target", agentLookup);
            return src === selectedAgentId || dst === selectedAgentId;
          })
          .slice()
          .sort((a, b) => toTimeNum(firstNonEmptyText([b && b.started_at, b && b.updated_at], "")) - toTimeNum(firstNonEmptyText([a && a.started_at, a && a.updated_at], "")));
        const detailMetaRows = [];
        if (selectedEntity) {
          detailMetaRows.push(["节点类型", selectedEntityType === "agent" ? "Agent" : (selectedEntityType === "channel" ? "通道" : "节点")]);
          if (selectedEntityType === "agent") {
            const agentState = classifyAgentState(selectedEntity);
            detailMetaRows.push(["运行状态", agentStateLabelLocal(agentState)]);
            detailMetaRows.push(["活跃关系", String(Number(relationHotByAgent.get(String((selectedEntity && selectedEntity.agent_id) || "").trim()) || 0))]);
            const sessionId = String(((selectedEntity && selectedEntity.meta && selectedEntity.meta.session_id) || selectedEntity.session_id || "")).trim();
            if (sessionId) detailMetaRows.push(["会话ID", shortId(sessionId)]);
          }
          const desc = firstNonEmptyText([
            selectedEntity && selectedEntity.desc,
            selectedEntity && selectedEntity.meta && selectedEntity.meta.desc,
            selectedEntity && selectedEntity.meta && selectedEntity.meta.channel_desc,
          ], "");
          if (desc) detailMetaRows.push(["说明", desc]);
        }
        if (mainMetaNode) {
          mainMetaNode.textContent = "view=组织认知页 · 节点=" + nodes.length + " · 可见Agent=" + agentRows.length + " · 运行态关系=" + relations.length + " · generated_at=" + DATA.generated_at;
        }

        const panel = el("section", { class: "org-overview-shell" });
        const top = el("div", { class: "org-overview-summary" });
        top.appendChild(chip("通道:" + channelBlocks.length, channelBlocks.length ? "good" : "muted"));
        top.appendChild(chip("Agent:" + agentRows.length, agentRows.length ? "good" : "muted"));
        top.appendChild(chip("活跃:" + stateCount.active, stateCount.active ? "good" : "muted"));
        top.appendChild(chip("运行态关系:" + relations.length, relations.length ? "warn" : "muted"));
        if (manualRelationsAll.length) top.appendChild(chip("人工关系:" + manualRelationsAll.length, "muted"));
        const fetchedAtText = compactDateTime(cache && cache.fetchedAt);
        if (fetchedAtText) top.appendChild(chip("更新:" + fetchedAtText, "muted"));
        panel.appendChild(top);

        const grid = el("div", { class: "org-overview-grid" });

        const treeCol = el("section", { class: "org-overview-col org-overview-tree" });
        treeCol.appendChild(el("div", { class: "org-overview-col-title", text: "组织树" }));
        if (!channelBlocks.length) {
          treeCol.appendChild(el("div", { class: "org-overview-empty", text: "当前暂无组织快照数据。" }));
        } else {
          channelBlocks.forEach((block) => {
            const section = el("div", { class: "org-overview-group" });
            const head = el("div", { class: "org-overview-group-head" });
            head.appendChild(el("div", { class: "org-overview-group-title", text: channelNodeLabel(block.row) }));
            head.appendChild(chip("Agent " + block.children.length, block.children.length ? "good" : "muted"));
            section.appendChild(head);
            const list = el("div", { class: "org-overview-agent-list" });
            if (!block.children.length) {
              list.appendChild(el("div", { class: "org-overview-empty mini", text: "当前通道暂无可见 Agent。" }));
            } else {
              block.children.forEach((row) => {
                const aid = String((row && row.agent_id) || "").trim();
                const stateKey = classifyAgentState(row);
                const hot = Number(relationHotByAgent.get(aid) || 0);
                const item = el("button", {
                  class: "org-overview-agent-item" + (aid && aid === selectedAgentId ? " active" : ""),
                  type: "button",
                });
                item.addEventListener("click", () => {
                  selectedAgentMap[pid] = aid;
                  render();
                });
                const left = el("div", { class: "org-overview-agent-main" });
                left.appendChild(el("div", { class: "org-overview-agent-name", text: normalizeOrgNodeLabel(row) }));
                item.appendChild(left);
                const meta = el("div", { class: "org-overview-agent-meta" });
                meta.appendChild(chip(agentStateLabelLocal(stateKey), agentStateToneLocal(stateKey)));
                if (hot) meta.appendChild(chip("活跃关系 " + hot, "warn"));
                item.appendChild(meta);
                list.appendChild(item);
              });
            }
            section.appendChild(list);
            treeCol.appendChild(section);
          });
        }
        grid.appendChild(treeCol);

        const mainCol = el("section", { class: "org-overview-col org-overview-main" });
        mainCol.appendChild(el("div", { class: "org-overview-col-title", text: "关系主视图" }));
        const mainIntro = el("div", { class: "org-overview-card org-overview-focus-card" });
        mainIntro.appendChild(el("div", { class: "org-overview-focus-title", text: selectedEntityLabel }));
        mainIntro.appendChild(el("div", {
          class: "org-overview-focus-sub",
          text: selectedEntityType === "agent"
            ? "当前聚焦该 Agent 的运行态协作关系，仅用于认知，不承担编辑。"
            : "当前展示组织级结构与最近运行态关系，用于稳定认知。"
        }));
        mainCol.appendChild(mainIntro);
        const relCard = el("div", { class: "org-overview-card" });
        const relHead = el("div", { class: "org-overview-card-head" });
        relHead.appendChild(el("div", { class: "org-overview-card-title", text: selectedEntityType === "agent" ? "关联运行态关系" : "最近运行态关系" }));
        relHead.appendChild(chip("共 " + relatedRuntime.length + " 条", relatedRuntime.length ? "warn" : "muted"));
        relCard.appendChild(relHead);
        const relList = el("div", { class: "org-overview-relation-list" });
        if (!relatedRuntime.length) {
          relList.appendChild(el("div", { class: "org-overview-empty", text: "当前筛选下暂无运行态关系。" }));
        } else {
          relatedRuntime.slice(0, 18).forEach((rel) => {
            const row = el("div", { class: "org-overview-relation-row" + (relationIsActive(rel) ? " active" : "") });
            row.appendChild(el("div", {
              class: "org-overview-relation-main org-overview-relation-title",
              text: labelForRuntimeAgent(nodes, rel, "source", agentLookup) + " → " + labelForRuntimeAgent(nodes, rel, "target", agentLookup),
            }));
            const sub = el("div", { class: "org-overview-relation-sub" });
            const reason = String((rel && rel.reason) || "").trim() || "runtime";
            sub.appendChild(chip(reason, relationIsActive(rel) ? "good" : "muted"));
            const due = compactDateTime(firstNonEmptyText([rel && rel.expires_at, rel && rel.updated_at], ""));
            if (due) sub.appendChild(chip("到期/更新 " + due, "muted"));
            row.appendChild(sub);
            relList.appendChild(row);
          });
        }
        relCard.appendChild(relList);
        mainCol.appendChild(relCard);
        grid.appendChild(mainCol);

        const detailCol = el("section", { class: "org-overview-col org-overview-detail" });
        detailCol.appendChild(el("div", { class: "org-overview-col-title", text: "节点详情" }));
        const detailCard = el("div", { class: "org-overview-card org-overview-detail-card" });
        detailCard.appendChild(el("div", { class: "org-overview-detail-title", text: selectedEntityLabel }));
        if (detailMetaRows.length) {
          const kv = el("div", { class: "org-overview-kv" });
          detailMetaRows.forEach(([label, value]) => {
            const row = el("div", { class: "org-overview-kv-row" });
            row.appendChild(el("div", { class: "org-overview-kv-label", text: String(label || "") }));
            row.appendChild(el("div", { class: "org-overview-kv-value", text: String(value || "-") }));
            kv.appendChild(row);
          });
          detailCard.appendChild(kv);
        } else {
          detailCard.appendChild(el("div", { class: "org-overview-empty", text: "选择左侧 Agent 后可查看节点详情。" }));
        }
        if (selectedEntityType === "agent" && selectedAgentId) {
          const relatedManual = manualRelationsAll.filter((rel) => {
            const src = String((rel && rel.source_agent_id) || "").trim();
            const dst = String((rel && rel.target_agent_id) || "").trim();
            return src === selectedAgentId || dst === selectedAgentId;
          });
          const note = el("div", { class: "org-overview-detail-note" });
          note.appendChild(chip("人工关系 " + relatedManual.length, "muted"));
          note.appendChild(chip("架构编辑已剥离", "muted"));
          detailCard.appendChild(note);
        }
        detailCol.appendChild(detailCard);
        grid.appendChild(detailCol);

        panel.appendChild(grid);
        listNode.appendChild(panel);
        return;
      }
      const selectedRelatedAgentIds = new Set();
      if (selectedAgentId) {
        selectedRelatedAgentIds.add(selectedAgentId);
        visibleRelations.forEach((rel) => {
          const src = resolveRuntimeAgentId(nodes, rel, "source", agentLookup);
          const dst = resolveRuntimeAgentId(nodes, rel, "target", agentLookup);
          if (src === selectedAgentId && dst) selectedRelatedAgentIds.add(dst);
          if (dst === selectedAgentId && src) selectedRelatedAgentIds.add(src);
        });
        visibleManualRelations.forEach((rel) => {
          const src = String((rel && rel.source_agent_id) || "").trim();
          const dst = String((rel && rel.target_agent_id) || "").trim();
          if (src === selectedAgentId && dst) selectedRelatedAgentIds.add(dst);
          if (dst === selectedAgentId && src) selectedRelatedAgentIds.add(src);
        });
      }
      if (mainMetaNode) {
        const prefix = isOrgView ? "view=组织视图" : "view=架构2D画板";
        const runtimePart = " · 运行态关系=" + visibleRelations.length + "/" + relations.length;
        const manualPart = allowManualEditing
          ? (" · 人工关系=" + visibleManualRelations.length + "/" + manualRelationsAll.length)
          : "";
        mainMetaNode.textContent = prefix
          + " · 节点=" + visibleNodes.length + "/" + nodes.length
          + " · 关系=" + edges.length
          + runtimePart
          + manualPart
          + " · generated_at=" + DATA.generated_at;
      }

      const stale = !cache || ((Date.now() - Number(cache.fetchedAtMs || 0)) > 10000);
      if (stale && !ORG_BOARD_UI.loadingByProject[pid]) {
        fetchOrgBoardData(pid, { maxAgeMs: 10000 }).then(() => render()).catch(() => {});
      }

      const panel = el("section", { class: "org-board-panel org-canvas-shell" });
      const stage = el("div", { class: "org-canvas-stage" });
      panel.appendChild(stage);

      const menu = el("div", { class: "org-floating-menu" });
      const refreshBtn = el("button", { class: "btn", text: ORG_BOARD_UI.loadingByProject[pid] ? "刷新中..." : (isOrgView ? "刷新组织" : "刷新架构") });
      refreshBtn.disabled = !!ORG_BOARD_UI.loadingByProject[pid];
      refreshBtn.addEventListener("click", () => {
        fetchOrgBoardData(pid, { force: true, maxAgeMs: 0 }).then(() => render()).catch(() => {});
      });
      menu.appendChild(refreshBtn);
      const resetViewBtn = el("button", { class: "btn", text: "复位视角" });
      resetViewBtn.disabled = true;
      menu.appendChild(resetViewBtn);
      const open3dBtn = el("button", { class: "btn", text: "打开3D图谱" });
      open3dBtn.addEventListener("click", () => openProjectOrg3D(pid));
      menu.appendChild(open3dBtn);
      const manualPanelOpenMap = ORG_BOARD_UI.manualPanelOpenByProject || (ORG_BOARD_UI.manualPanelOpenByProject = Object.create(null));
      let manualPanelOpen = !!manualPanelOpenMap[pid];
      if (!allowManualEditing && manualPanelOpen) {
        manualPanelOpenMap[pid] = false;
        manualPanelOpen = false;
      }
      if (allowManualEditing) {
        const relationManageBtn = el("button", { class: "btn", text: manualPanelOpen ? "关闭关系管理" : "关系管理" });
        relationManageBtn.addEventListener("click", () => {
          manualPanelOpenMap[pid] = !manualPanelOpen;
          render();
        });
        menu.appendChild(relationManageBtn);
      }
      stage.appendChild(menu);

      const centerTools = el("div", { class: "org-floating-center-tools" });

      const stats = el("div", { class: "org-floating-stats chips" });
      stats.appendChild(chip("节点:" + visibleNodes.length + "/" + nodes.length, nodes.length ? "good" : "muted"));
      stats.appendChild(chip("Agent:" + allAgentNodes.length, allAgentNodes.length ? "good" : "muted"));
      stats.appendChild(chip("活跃:" + stateCount.active, stateCount.active ? "good" : "muted"));
      stats.appendChild(chip("空闲:" + stateCount.idle, "muted"));
      stats.appendChild(chip("废弃:" + stateCount.legacy, stateCount.legacy ? "warn" : "muted"));
      stats.appendChild(chip("结构边:" + edges.length, "muted"));
      stats.appendChild(chip("运行态关系:" + visibleRelations.length + "/" + relations.length, visibleRelations.length ? "warn" : "muted"));
      stats.appendChild(chip("活跃关系:" + visibleActiveRelations.length, visibleActiveRelations.length ? "good" : "muted"));
      const fetchedAtText = compactDateTime(cache && cache.fetchedAt);
      if (fetchedAtText) stats.appendChild(chip("更新:" + fetchedAtText, "muted"));
      centerTools.appendChild(stats);

      const filterBar = el("div", { class: "org-floating-agent-filter" });
      [
        ["all", "Agent:全部"],
        ["active", "活跃"],
        ["idle", "空闲"],
        ["legacy", "废弃"],
      ].forEach(([value, label]) => {
        const isActive = value === "all"
          ? selectedAgentStates.size === AGENT_FILTER_KEYS.length
          : selectedAgentStates.has(value);
        const btn = el("button", {
          class: "chipbtn" + (isActive ? " active" : ""),
          type: "button",
          text: label,
          title: "筛选 Agent 状态：" + label,
        });
        btn.addEventListener("click", () => {
          if (value === "all") {
            const nextAll = new Set();
            AGENT_FILTER_KEYS.forEach((k) => nextAll.add(k));
            persistAgentFilterSelection(nextAll);
            render();
            return;
          }
          const next = new Set(selectedAgentStates);
          if (next.has(value)) next.delete(value);
          else next.add(value);
          if (!next.size) AGENT_FILTER_KEYS.forEach((k) => next.add(k));
          persistAgentFilterSelection(next);
          render();
        });
        filterBar.appendChild(btn);
      });
      centerTools.appendChild(filterBar);

      if (allowManualEditing) {
        const matterFilterBar = el("div", { class: "org-floating-matter-filter" });
        const allSelectedMatter = relFilter.size === REL_MATTER_KEYS.length;
        const allBtn = el("button", {
          class: "chipbtn" + (allSelectedMatter ? " active" : ""),
          type: "button",
          text: "事项:全部",
        });
        allBtn.addEventListener("click", () => {
          const next = new Set();
          REL_MATTER_KEYS.forEach((k) => next.add(k));
          persistMatterSelection(next);
          render();
        });
        matterFilterBar.appendChild(allBtn);
        REL_MATTER_KEYS.forEach((key) => {
          const count = Number(matterCountByType[key] || 0);
          const btn = el("button", {
            class: "chipbtn matter-chip matter-" + key + (relFilter.has(key) ? " active" : ""),
            type: "button",
            text: String(REL_MATTER_LABEL[key] || key) + ":" + count,
            title: "筛选事项类型：" + String(REL_MATTER_LABEL[key] || key),
          });
          btn.addEventListener("click", () => {
            const next = new Set(relFilter);
            if (next.has(key)) next.delete(key);
            else next.add(key);
            if (!next.size) REL_MATTER_KEYS.forEach((k) => next.add(k));
            persistMatterSelection(next);
            render();
          });
          matterFilterBar.appendChild(btn);
        });
        centerTools.appendChild(matterFilterBar);

        const manualFilterBar = el("div", { class: "org-floating-manual-filter" });
        const allSelectedManual = selectedManualTypes.size === manualTypeIds.length;
        const manualAllBtn = el("button", {
          class: "chipbtn" + (allSelectedManual ? " active" : ""),
          type: "button",
          text: "人工关系:全部",
        });
        manualAllBtn.disabled = !manualTypeIds.length;
        manualAllBtn.addEventListener("click", () => {
          const next = new Set();
          manualTypeIds.forEach((id) => next.add(id));
          persistManualTypeSelection(next);
          render();
        });
        manualFilterBar.appendChild(manualAllBtn);
        if (!manualTypeIds.length) {
          manualFilterBar.appendChild(chip("未定义", "muted"));
        } else {
          manualTypes.forEach((tp) => {
            const typeId = String((tp && tp.id) || "").trim();
            if (!typeId) return;
            const count = Number(manualCountByType[typeId] || 0);
            const btn = el("button", {
              class: "chipbtn manual-chip" + (selectedManualTypes.has(typeId) ? " active" : ""),
              type: "button",
              text: String(tp.name || "关系") + ":" + count,
              title: "筛选人工关系：" + String(tp.name || "关系"),
            });
            const color = String((tp && tp.color) || "").trim();
            if (color) {
              btn.style.borderColor = color + "66";
              btn.style.color = color;
              if (!selectedManualTypes.has(typeId)) btn.style.background = color + "1A";
            }
            btn.addEventListener("click", () => {
              const next = new Set(selectedManualTypes);
              if (next.has(typeId)) next.delete(typeId);
              else next.add(typeId);
              if (!next.size) manualTypeIds.forEach((id) => next.add(id));
              persistManualTypeSelection(next);
              render();
            });
            manualFilterBar.appendChild(btn);
          });
        }
        centerTools.appendChild(manualFilterBar);
      } else {
        const orgHintBar = el("div", { class: "org-floating-matter-filter" });
        orgHintBar.appendChild(chip("组织视图仅展示活跃运行态关系", "muted"));
        orgHintBar.appendChild(chip("切换到“架构”可管理人工关系", "muted"));
        centerTools.appendChild(orgHintBar);
      }
      stage.appendChild(centerTools);

      const err = String(ORG_BOARD_UI.errorByProject[pid] || "").trim();
      const note = String(ORG_BOARD_UI.noteByProject[pid] || "").trim();
      if (err) {
        stage.appendChild(el("div", {
          class: "org-floating-alert is-error",
          text: "组织画板加载异常：" + err,
        }));
      } else if (note) {
        stage.appendChild(el("div", {
          class: "org-floating-alert",
          text: note,
        }));
      }

      const boardWrap = el("div", { class: "org-board-wrap org-board-wrap-floating" });
      const board = el("div", { class: "org-board-canvas org-board-canvas-stage" });
      const panLayer = el("div", { class: "org-board-pan-layer" });
      board.appendChild(panLayer);
      boardWrap.appendChild(board);
      stage.appendChild(boardWrap);
      listNode.appendChild(panel);

      if (!nodes.length) {
        const text = ORG_BOARD_UI.loadingByProject[pid]
          ? (isOrgView ? "正在加载组织节点与运行态关系..." : "正在加载架构快照与关系数据...")
          : (isOrgView ? "当前项目暂无可展示组织节点，请先完成组织快照接线后刷新。" : "当前项目暂无架构快照数据，请先完成接线后刷新。");
        stage.appendChild(el("div", { class: "org-empty-state", text }));
        return;
      }

      const stageRect = stage.getBoundingClientRect();
      const width = Math.max(760, Math.round(Number(stageRect.width || 0) || Number(listNode.clientWidth || 0) || 980));
      const height = Math.max(
        460,
        Math.round(Number(stageRect.height || 0) || Math.max(0, window.innerHeight - 260) || 560),
      );
      const maxPanX = Math.max(120, Math.round(width * 0.38));
      const maxPanY = Math.max(80, Math.round(height * 0.34));
      const viewportMap = ORG_BOARD_UI.viewportByProject || (ORG_BOARD_UI.viewportByProject = Object.create(null));
      const viewport = viewportMap[pid] && typeof viewportMap[pid] === "object"
        ? viewportMap[pid]
        : { x: 0, y: 0 };
      const clampPan = (value, limit) => Math.max(-limit, Math.min(limit, Number(value) || 0));
      const applyPan = (x, y) => {
        const nx = clampPan(x, maxPanX);
        const ny = clampPan(y, maxPanY);
        viewport.x = nx;
        viewport.y = ny;
        viewportMap[pid] = viewport;
        panLayer.style.transform = "translate3d(" + nx.toFixed(1) + "px," + ny.toFixed(1) + "px,0)";
      };
      applyPan(viewport.x, viewport.y);
      resetViewBtn.disabled = false;
      resetViewBtn.addEventListener("click", () => {
        applyPan(0, 0);
      });
      let dragState = null;
      let suppressBoardClick = false;
      const pointerAllowed = (evt) => {
        if (!evt) return false;
        if (evt.pointerType === "mouse" && Number(evt.button) !== 0) return false;
        return true;
      };
      board.addEventListener("pointerdown", (evt) => {
        if (!pointerAllowed(evt)) return;
        if (linkDraft) return;
        const target = evt && evt.target;
        if (target && typeof target.closest === "function" && target.closest("button,a,input,textarea,select,label,summary,details")) return;
        if (target && typeof target.closest === "function" && target.closest(".org-node")) return;
        dragState = {
          id: evt.pointerId,
          startX: Number(viewport.x) || 0,
          startY: Number(viewport.y) || 0,
          clientX: Number(evt.clientX) || 0,
          clientY: Number(evt.clientY) || 0,
          moved: false,
        };
        board.classList.add("is-dragging");
        if (typeof board.setPointerCapture === "function") {
          try { board.setPointerCapture(evt.pointerId); } catch (_) {}
        }
        evt.preventDefault();
      });
      board.addEventListener("pointermove", (evt) => {
        if (linkDraft) {
          const p = boardPointFromClient(evt && evt.clientX, evt && evt.clientY);
          linkDraftMap[pid] = Object.assign({}, linkDraft, {
            pointer_x: Number(p.x || 0),
            pointer_y: Number(p.y || 0),
          });
          render();
          return;
        }
        if (!dragState || dragState.id !== evt.pointerId) return;
        const dx = (Number(evt.clientX) || 0) - dragState.clientX;
        const dy = (Number(evt.clientY) || 0) - dragState.clientY;
        if (Math.abs(dx) + Math.abs(dy) > 3) dragState.moved = true;
        applyPan(dragState.startX + dx, dragState.startY + dy);
      });
      const finishDrag = (evt) => {
        if (!dragState || (evt && dragState.id !== evt.pointerId)) return;
        suppressBoardClick = !!dragState.moved;
        dragState = null;
        board.classList.remove("is-dragging");
      };
      board.addEventListener("pointerup", finishDrag);
      board.addEventListener("pointercancel", finishDrag);
      board.addEventListener("lostpointercapture", finishDrag);
      board.addEventListener("click", (evt) => {
        if (suppressBoardClick) {
          suppressBoardClick = false;
          return;
        }
        if (linkDraft) {
          clearLinkDraft();
          ORG_BOARD_UI.noteByProject[pid] = "已取消连线。";
          render();
          return;
        }
        const target = evt && evt.target;
        if (target && typeof target.closest === "function" && target.closest(".org-node")) return;
        if (!selectedAgentId) return;
        selectedAgentMap[pid] = "";
        render();
      });

      const layoutRows = buildOrgBoardLayout(visibleNodes, width, height);
      const posByNodeId = new Map();
      const posByAgentId = new Map();
      layoutRows.forEach((item) => {
        const nodeId = String((item && item.row && item.row.node_id) || "");
        if (nodeId) posByNodeId.set(nodeId, { x: Number(item.x || 0), y: Number(item.y || 0), row: item.row });
        const aid = String((item && item.row && item.row.agent_id) || "").trim();
        if (aid) posByAgentId.set(aid, { x: Number(item.x || 0), y: Number(item.y || 0), row: item.row });
      });
      const nodeLinkAnchor = (agentId, side) => {
        const aid = String(agentId || "").trim();
        if (!aid) return null;
        const pos = posByAgentId.get(aid);
        if (!pos) return null;
        const s = String(side || "right").trim().toLowerCase();
        const offX = s === "left" ? -86 : (s === "right" ? 86 : 0);
        const offY = s === "top" ? -24 : (s === "bottom" ? 24 : 0);
        return { x: Number(pos.x || 0) + offX, y: Number(pos.y || 0) + offY };
      };
      const boardPointFromClient = (clientX, clientY) => {
        const rect = board.getBoundingClientRect();
        const px = Number(clientX || 0) - Number(rect.left || 0) - Number(viewport.x || 0);
        const py = Number(clientY || 0) - Number(rect.top || 0) - Number(viewport.y || 0);
        return { x: px, y: py };
      };
      const clearLinkDraft = () => {
        delete linkDraftMap[pid];
      };
      const clearLinkEditor = () => {
        delete linkEditorMap[pid];
      };
      const curvePath = (x1, y1, x2, y2, bend) => {
        const sx = Number(x1 || 0);
        const sy = Number(y1 || 0);
        const tx = Number(x2 || 0);
        const ty = Number(y2 || 0);
        const dx = tx - sx;
        const dy = ty - sy;
        const len = Math.max(1, Math.hypot(dx, dy));
        const nx = -dy / len;
        const ny = dx / len;
        const mx = (sx + tx) / 2;
        const my = (sy + ty) / 2;
        const offset = Number(bend || 0);
        const cx = mx + nx * offset;
        const cy = my + ny * offset;
        return {
          d: "M " + sx.toFixed(1) + " " + sy.toFixed(1) + " Q " + cx.toFixed(1) + " " + cy.toFixed(1) + " " + tx.toFixed(1) + " " + ty.toFixed(1),
          midX: 0.25 * sx + 0.5 * cx + 0.25 * tx,
          midY: 0.25 * sy + 0.5 * cy + 0.25 * ty,
        };
      };

      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("class", "org-board-svg");
      svg.setAttribute("viewBox", "0 0 " + width + " " + height);
      svg.setAttribute("preserveAspectRatio", "none");
      const drawEdges = [];
      edges.forEach((edge) => {
        const src = posByNodeId.get(String((edge && edge.source_node_id) || ""));
        const dst = posByNodeId.get(String((edge && edge.target_node_id) || ""));
        if (!src || !dst) return;
        const srcAid = String((src.row && src.row.agent_id) || "").trim();
        const dstAid = String((dst.row && dst.row.agent_id) || "").trim();
        let edgeClass = "org-edge org-edge-struct data-edge";
        if (selectedAgentId) {
          if (srcAid === selectedAgentId || dstAid === selectedAgentId) edgeClass += " is-selected";
          else edgeClass += " is-dimmed";
        }
        drawEdges.push({
          layer: "struct",
          order: 1,
          sourceKey: "node:" + String((edge && edge.source_node_id) || ""),
          targetKey: "node:" + String((edge && edge.target_node_id) || ""),
          x1: src.x,
          y1: src.y,
          x2: dst.x,
          y2: dst.y,
          edgeClass,
          label: "",
          color: "",
          width: 1.4,
          style: "solid",
          active: false,
          stableKey: "struct:" + String((edge && edge.source_node_id) || "") + "->" + String((edge && edge.target_node_id) || ""),
        });
      });
      const runtimePairMap = new Map();
      visibleRelations.forEach((rel) => {
        const srcAid = resolveRuntimeAgentId(visibleNodes, rel, "source", agentLookup);
        const dstAid = resolveRuntimeAgentId(visibleNodes, rel, "target", agentLookup);
        if (!srcAid || !dstAid || srcAid === dstAid) return;
        const startedTs = toTimeNum(firstNonEmptyText([rel && rel.started_at, rel && rel.updated_at], ""));
        const active = relationIsActive(rel);
        const matter = classifyRelationMatter(rel);
        const key = srcAid + "->" + dstAid + "::" + matter;
        const cur = runtimePairMap.get(key);
        if (!cur || (active && !cur.active) || (active === cur.active && startedTs >= Number(cur.startedTs || 0))) {
          runtimePairMap.set(key, { srcAid, dstAid, active, startedTs, matter });
        }
      });
      runtimePairMap.forEach((item) => {
        const src = posByAgentId.get(String(item.srcAid || "").trim());
        const dst = posByAgentId.get(String(item.dstAid || "").trim());
        if (!src || !dst) return;
        let edgeClass = "org-edge org-edge-runtime data-edge matter-" + String(item.matter || "other") + (item.active ? " active" : "");
        if (selectedAgentId) {
          if (item.srcAid === selectedAgentId || item.dstAid === selectedAgentId) edgeClass += " is-selected";
          else edgeClass += " is-dimmed";
        }
        drawEdges.push({
          layer: "runtime",
          order: 2,
          sourceKey: "agent:" + String(item.srcAid || ""),
          targetKey: "agent:" + String(item.dstAid || ""),
          x1: src.x,
          y1: src.y,
          x2: dst.x,
          y2: dst.y,
          edgeClass,
          label: "",
          color: "",
          width: 1.9,
          style: "dash",
          active: !!item.active,
          bendBase: Number(REL_MATTER_OFFSET_Y[String(item.matter || "other")] || 0),
          stableKey: "runtime:" + String(item.srcAid || "") + "->" + String(item.dstAid || "") + ":" + String(item.matter || "other"),
        });
      });
      visibleManualRelations.forEach((rel) => {
        const srcAid = String((rel && rel.source_agent_id) || "").trim();
        const dstAid = String((rel && rel.target_agent_id) || "").trim();
        const typeId = String((rel && rel.relation_type_id) || "").trim();
        if (!srcAid || !dstAid || !typeId) return;
        const src = posByAgentId.get(srcAid);
        const dst = posByAgentId.get(dstAid);
        if (!src || !dst) return;
        const typeRow = manualTypeById.get(typeId);
        let edgeClass = "org-edge org-edge-manual";
        if (selectedAgentId) {
          if (srcAid === selectedAgentId || dstAid === selectedAgentId) edgeClass += " is-selected";
          else edgeClass += " is-dimmed";
        }
        drawEdges.push({
          layer: "manual",
          order: 3,
          sourceKey: "agent:" + srcAid,
          targetKey: "agent:" + dstAid,
          x1: src.x,
          y1: src.y,
          x2: dst.x,
          y2: dst.y,
          edgeClass,
          label: String((typeRow && typeRow.name) || "关系"),
          color: String((typeRow && typeRow.color) || "").trim() || "#2f6fed",
          width: Math.max(3.2, Number((typeRow && typeRow.line_width) || 4.2) || 4.2),
          style: String((typeRow && typeRow.line_style) || "solid"),
          active: true,
          stableKey: "manual:" + String(rel.id || srcAid + "->" + dstAid + ":" + typeId),
        });
      });
      if (linkDraft) {
        const sourceAid = String((linkDraft && linkDraft.source_agent_id) || "").trim();
        const sourceSide = String((linkDraft && linkDraft.source_side) || "right").trim().toLowerCase();
        const anchor = nodeLinkAnchor(sourceAid, sourceSide);
        if (anchor) {
          drawEdges.push({
            layer: "draft",
            order: 4,
            sourceKey: "draft:" + sourceAid + ":" + sourceSide,
            targetKey: "draft:pointer",
            x1: Number(anchor.x || 0),
            y1: Number(anchor.y || 0),
            x2: Number((linkDraft && linkDraft.pointer_x) || anchor.x || 0),
            y2: Number((linkDraft && linkDraft.pointer_y) || anchor.y || 0),
            edgeClass: "org-edge org-edge-draft active",
            label: "",
            color: "#2f6fed",
            width: 2.2,
            style: "dash",
            active: true,
            bendBase: 0,
            stableKey: "draft:" + sourceAid,
          });
        }
      }
      const pairMap = new Map();
      drawEdges.forEach((edgeItem) => {
        const a = String(edgeItem.sourceKey || "").trim();
        const b = String(edgeItem.targetKey || "").trim();
        if (!a || !b) return;
        const key = a < b ? (a + "::" + b) : (b + "::" + a);
        if (!pairMap.has(key)) pairMap.set(key, []);
        pairMap.get(key).push(edgeItem);
      });
      pairMap.forEach((list) => {
        list.sort((a, b) => {
          const oa = Number(a.order || 0);
          const ob = Number(b.order || 0);
          if (oa !== ob) return oa - ob;
          return String(a.stableKey || "").localeCompare(String(b.stableKey || ""));
        });
        const n = list.length;
        list.forEach((row, idx) => {
          row.slot = idx - (n - 1) / 2;
        });
      });
      drawEdges
        .slice()
        .sort((a, b) => Number(a.order || 0) - Number(b.order || 0))
        .forEach((row) => {
          const layerBase = row.layer === "manual" ? 22 : (row.layer === "runtime" ? 14 : 8);
          const bend = Number(row.bendBase || 0) + Number(row.slot || 0) * 12 + layerBase;
          const curve = curvePath(row.x1, row.y1, row.x2, row.y2, bend);
          const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
          path.setAttribute("d", curve.d);
          path.setAttribute("class", String(row.edgeClass || "org-edge"));
          if (row.color) path.setAttribute("stroke", String(row.color));
          path.setAttribute("stroke-width", String(Number(row.width || 1.5).toFixed(2)));
          if (String(row.style || "").toLowerCase() === "dash") path.setAttribute("stroke-dasharray", "6 4");
          if (String(row.style || "").toLowerCase() === "dot") path.setAttribute("stroke-dasharray", "3 5");
          svg.appendChild(path);
          if (row.layer === "manual" && row.label) {
            const txt = document.createElementNS("http://www.w3.org/2000/svg", "text");
            txt.setAttribute("class", "org-edge-label manual");
            txt.setAttribute("x", Number(curve.midX || 0).toFixed(1));
            txt.setAttribute("y", Number((curve.midY || 0) - 3).toFixed(1));
            txt.textContent = String(row.label || "");
            if (row.color) txt.setAttribute("fill", String(row.color));
            svg.appendChild(txt);
          }
        });
      panLayer.appendChild(svg);

      const runtimeHotByAgent = relationHotByAgent;
      const setSelectedAgent = (aid) => {
        const next = String(aid || "").trim();
        selectedAgentMap[pid] = next && next !== selectedAgentId ? next : "";
        render();
      };
      const agentStateLabel = (st) => {
        const key = String(st || "").trim();
        if (key === "active") return "活跃";
        if (key === "legacy") return "废弃";
        return "空闲";
      };
      const agentStateTone = (st) => {
        const key = String(st || "").trim();
        if (key === "active") return "good";
        if (key === "legacy") return "warn";
        return "muted";
      };
      const openLinkEditor = (sourceAid, targetAid) => {
        const src = String(sourceAid || "").trim();
        const dst = String(targetAid || "").trim();
        if (!src || !dst || src === dst) return;
        const firstType = manualTypes[0] || null;
        const next = {
          source_agent_id: src,
          target_agent_id: dst,
          relation_type_id: String((firstType && firstType.id) || ""),
          type_name: "",
          color: String((firstType && firstType.color) || "#2f6fed"),
          line_style: String((firstType && firstType.line_style) || "solid"),
          line_width: Number((firstType && firstType.line_width) || 4.2) || 4.2,
        };
        linkEditorMap[pid] = next;
      };
      const startLinkDraftFromAgent = (sourceAid, sourceSide, evt) => {
        const aid = String(sourceAid || "").trim();
        if (!aid) return;
        const side = String(sourceSide || "right").trim().toLowerCase();
        const anchor = nodeLinkAnchor(aid, side);
        if (!anchor) return;
        const p = boardPointFromClient(evt && evt.clientX, evt && evt.clientY);
        linkDraftMap[pid] = {
          source_agent_id: aid,
          source_side: side,
          pointer_x: Number(p.x || anchor.x || 0),
          pointer_y: Number(p.y || anchor.y || 0),
        };
        clearLinkEditor();
        ORG_BOARD_UI.noteByProject[pid] = "连线中：请选择目标 Agent。";
        render();
      };
      const submitLinkEditor = () => {
        const draft = linkEditorMap[pid] && typeof linkEditorMap[pid] === "object" ? linkEditorMap[pid] : null;
        if (!draft) return;
        try {
          const sourceAid = String(draft.source_agent_id || "").trim();
          const targetAid = String(draft.target_agent_id || "").trim();
          if (!sourceAid || !targetAid || sourceAid === targetAid) {
            alert("源/目标 Agent 无效，请重试。");
            return;
          }
          let relationTypeId = String(draft.relation_type_id || "").trim();
          const selectedType = relationTypeId ? (manualTypeById.get(relationTypeId) || null) : null;
          const customTypeName = String(draft.type_name || "").trim();
          const color = String(draft.color || "").trim() || "#2f6fed";
          const lineStyle = normalizeOrgRelationLineStyle(draft.line_style);
          const lineWidth = normalizeOrgRelationLineWidth(draft.line_width, 4.2);
          if (customTypeName) {
            const type = ensureOrgRelationTypeForProject(pid, customTypeName, color, {
              line_style: lineStyle,
              line_width: lineWidth,
            });
            relationTypeId = String((type && type.id) || "").trim();
          } else if (selectedType) {
            const type = ensureOrgRelationTypeForProject(pid, String(selectedType.name || "").trim(), color, {
              line_style: lineStyle,
              line_width: lineWidth,
            });
            relationTypeId = String((type && type.id) || "").trim();
          }
          if (!relationTypeId) {
            alert("请选择关系类型或输入新关系类型。");
            return;
          }
          addOrgManualRelation(pid, {
            source_agent_id: sourceAid,
            target_agent_id: targetAid,
            relation_type_id: relationTypeId,
          });
          selectedAgentMap[pid] = targetAid;
          clearLinkDraft();
          clearLinkEditor();
          ORG_BOARD_UI.noteByProject[pid] = "已新增人工关系（直连）。";
          render();
        } catch (e) {
          alert("新增关系失败：" + String((e && e.message) || e || "未知错误"));
        }
      };

      layoutRows.forEach((item) => {
        const row = (item && item.row) || {};
        const nodeType = orgNodeType(row);
        const label = normalizeOrgNodeLabel(row);
        const node = el("div", {
          class: "org-node type-" + nodeType,
          title: label,
          style: "left:" + Number(item.x || 0).toFixed(1) + "px;top:" + Number(item.y || 0).toFixed(1) + "px;",
        });
        const badge = el("span", { class: "org-node-label", text: label });
        node.appendChild(badge);
        const aid = String((row && row.agent_id) || "").trim();
        const hot = Number(runtimeHotByAgent.get(aid) || 0);
        if (hot > 0) {
          node.classList.add("active");
          node.appendChild(el("span", { class: "org-node-hot", text: String(hot) }));
        }
        if (nodeType === "agent") {
          const stateClass = classifyAgentState(row);
          node.classList.add("status-" + stateClass, "selectable");
          node.setAttribute("tabindex", "0");
          node.setAttribute("role", "button");
          node.setAttribute("aria-label", label + "（" + agentStateLabel(stateClass) + "）");
          if (selectedAgentId === aid) node.classList.add("selected");
          else if (selectedAgentId) {
            if (selectedRelatedAgentIds.has(aid)) node.classList.add("related");
            else node.classList.add("dimmed");
          }
          const linkHandleSides = [
            ["top", "上"],
            ["right", "右"],
            ["bottom", "下"],
            ["left", "左"],
          ];
          linkHandleSides.forEach(([side, labelText]) => {
            const handle = el("button", {
              class: "org-link-handle side-" + side,
              type: "button",
              text: "",
              title: "从" + label + "向" + labelText + "侧开始连线",
              "aria-label": "连线起点：" + label + "（" + labelText + "）",
            });
            handle.addEventListener("pointerdown", (evt) => {
              evt.preventDefault();
              evt.stopPropagation();
            });
            handle.addEventListener("click", (evt) => {
              evt.preventDefault();
              evt.stopPropagation();
              startLinkDraftFromAgent(aid, side, evt);
            });
            node.appendChild(handle);
          });
          node.addEventListener("pointerdown", (evt) => evt.stopPropagation());
          node.addEventListener("click", (evt) => {
            evt.preventDefault();
            evt.stopPropagation();
            if (linkDraft) {
              const srcAid = String((linkDraft && linkDraft.source_agent_id) || "").trim();
              if (!srcAid || srcAid === aid) {
                clearLinkDraft();
                ORG_BOARD_UI.noteByProject[pid] = "已取消连线。";
                render();
                return;
              }
              openLinkEditor(srcAid, aid);
              clearLinkDraft();
              ORG_BOARD_UI.noteByProject[pid] = "";
              render();
              return;
            }
            setSelectedAgent(aid);
          });
          node.addEventListener("keydown", (evt) => {
            if (!evt || (evt.key !== "Enter" && evt.key !== " ")) return;
            evt.preventDefault();
            evt.stopPropagation();
            setSelectedAgent(aid);
          });
        } else if (selectedAgentId) {
          node.classList.add("dimmed");
        }
        panLayer.appendChild(node);
      });

      const selectedAgentNode = selectedAgentId
        ? allAgentNodes.find((row) => String((row && row.agent_id) || "").trim() === selectedAgentId)
        : null;
      const selectedAgentGraphNode = selectedAgentId
        ? (graphAgentNodeBySession.get(selectedAgentId) || null)
        : null;
      const selectedAgentNodeId = String(
        ((selectedAgentNode && selectedAgentNode.node_id) || (selectedAgentGraphNode && selectedAgentGraphNode.id) || "")
      ).trim();
      const selectedRuntimeRows = selectedAgentId
        ? visibleRelationsRaw.filter((rel) => {
            const srcAid = resolveRuntimeAgentId(nodes, rel, "source", agentLookup);
            const dstAid = resolveRuntimeAgentId(nodes, rel, "target", agentLookup);
            return srcAid === selectedAgentId || dstAid === selectedAgentId;
          })
        : [];
      const selectedInboundRows = selectedAgentId
        ? selectedRuntimeRows.filter((rel) => resolveRuntimeAgentId(nodes, rel, "target", agentLookup) === selectedAgentId)
        : [];
      const selectedOutboundRows = selectedAgentId
        ? selectedRuntimeRows.filter((rel) => resolveRuntimeAgentId(nodes, rel, "source", agentLookup) === selectedAgentId)
        : [];
      const selectedActiveRows = selectedRuntimeRows.filter((rel) => relationIsActive(rel));
      const peerAidSet = new Set();
      selectedRuntimeRows.forEach((rel) => {
        const srcAid = resolveRuntimeAgentId(nodes, rel, "source", agentLookup);
        const dstAid = resolveRuntimeAgentId(nodes, rel, "target", agentLookup);
        if (srcAid === selectedAgentId && dstAid) peerAidSet.add(dstAid);
        if (dstAid === selectedAgentId && srcAid) peerAidSet.add(srcAid);
      });
      const reasonStats = new Map();
      selectedRuntimeRows.forEach((rel) => {
        const reason = String((rel && rel.reason) || "").trim() || "runtime";
        reasonStats.set(reason, Number(reasonStats.get(reason) || 0) + 1);
      });
      const reasonList = Array.from(reasonStats.entries())
        .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0))
        .slice(0, 6);
      const peerLabelRows = Array.from(peerAidSet)
        .map((aid) => {
          const row = allAgentNodes.find((it) => String((it && it.agent_id) || "").trim() === String(aid || "").trim());
          return {
            aid: String(aid || "").trim(),
            label: row ? normalizeOrgNodeLabel(row) : shortId(aid),
          };
        })
        .filter((it) => !!it.aid);
      const selectedAgentRunIds = (
        selectedAgentNodeId
        && graphIndex
        && graphIndex.agent_runs
        && Array.isArray(graphIndex.agent_runs[selectedAgentNodeId])
      ) ? graphIndex.agent_runs[selectedAgentNodeId] : [];
      const agentPanel = el("aside", { class: "org-agent-panel org-floating-agent-panel" + (selectedAgentId ? "" : " is-empty") });
      const panelHead = el("div", { class: "org-agent-panel-head" });
      const panelTitle = el("div", { class: "org-agent-panel-title", text: "Agent详情" });
      panelHead.appendChild(panelTitle);
      const panelClose = el("button", { class: "btn", type: "button", text: "关闭" });
      panelClose.disabled = !selectedAgentId;
      panelClose.addEventListener("click", () => {
        if (!selectedAgentId) return;
        selectedAgentMap[pid] = "";
        render();
      });
      panelHead.appendChild(panelClose);
      agentPanel.appendChild(panelHead);
      if (!selectedAgentId || !selectedAgentNode) {
        agentPanel.appendChild(el("div", {
          class: "org-agent-empty",
          text: "点击画板中的 Agent 节点可查看详情（基本信息/状态/关联/统计）。",
        }));
      } else {
        const stateKey = classifyAgentState(selectedAgentNode);
        const sectionBasic = el("div", { class: "org-agent-section" });
        sectionBasic.appendChild(el("div", { class: "org-agent-section-title", text: "基本信息" }));
        const basicGrid = el("div", { class: "org-agent-kv-grid" });
        const appendKV = (host, k, v) => {
          host.appendChild(el("div", { class: "org-agent-k", text: String(k || "") }));
          host.appendChild(el("div", { class: "org-agent-v", text: String(v || "-") }));
        };
        const channelName = firstNonEmptyText([
          selectedAgentNode && selectedAgentNode.meta && selectedAgentNode.meta.channel_name,
          selectedAgentGraphNode && selectedAgentGraphNode.channel_name,
        ], "");
        const sessionAlias = firstNonEmptyText([
          selectedAgentGraphNode && selectedAgentGraphNode.session_alias,
          selectedAgentNode && selectedAgentNode.meta && selectedAgentNode.meta.session_alias,
        ], "");
        const cliType = firstNonEmptyText([
          selectedAgentNode && selectedAgentNode.meta && selectedAgentNode.meta.cli_type,
          selectedAgentGraphNode && selectedAgentGraphNode.cli_type,
        ], "codex");
        const sourceType = firstNonEmptyText([
          selectedAgentNode && selectedAgentNode.meta && selectedAgentNode.meta.source,
          selectedAgentGraphNode && selectedAgentGraphNode.source,
        ], "unknown");
        const levelTag = firstNonEmptyText([
          selectedAgentNode && selectedAgentNode.meta && selectedAgentNode.meta.level,
        ], "");
        appendKV(basicGrid, "名称", normalizeOrgNodeLabel(selectedAgentNode));
        appendKV(basicGrid, "通道", channelName || "-");
        appendKV(basicGrid, "Session", selectedAgentId);
        appendKV(basicGrid, "CLI", cliType || "codex");
        appendKV(basicGrid, "别名", sessionAlias || "-");
        appendKV(basicGrid, "来源", sourceType || "unknown");
        appendKV(basicGrid, "层级", levelTag || "-");
        sectionBasic.appendChild(basicGrid);
        const statusChips = el("div", { class: "chips" });
        statusChips.appendChild(chip("状态:" + agentStateLabel(stateKey), agentStateTone(stateKey)));
        const runStatus = firstNonEmptyText([
          selectedAgentGraphNode && selectedAgentGraphNode.current_run_status,
        ], "");
        if (runStatus) statusChips.appendChild(chip("运行:" + runStatus, runStatus === "running" ? "good" : "muted"));
        const runAt = compactDateTime(firstNonEmptyText([
          selectedAgentGraphNode && selectedAgentGraphNode.current_run_at,
        ], ""));
        if (runAt) statusChips.appendChild(chip("最近运行:" + runAt, "muted"));
        sectionBasic.appendChild(statusChips);
        agentPanel.appendChild(sectionBasic);

        const sectionStats = el("div", { class: "org-agent-section" });
        sectionStats.appendChild(el("div", { class: "org-agent-section-title", text: "统计信息" }));
        const statGrid = el("div", { class: "org-agent-kv-grid" });
        appendKV(statGrid, "运行态关系", String(selectedRuntimeRows.length));
        appendKV(statGrid, "活跃关系", String(selectedActiveRows.length));
        appendKV(statGrid, "出向关系", String(selectedOutboundRows.length));
        appendKV(statGrid, "入向关系", String(selectedInboundRows.length));
        appendKV(statGrid, "关联Agent", String(peerLabelRows.length));
        appendKV(statGrid, "关联Run", String(selectedAgentRunIds.length));
        sectionStats.appendChild(statGrid);
        agentPanel.appendChild(sectionStats);

        const sectionLink = el("div", { class: "org-agent-section" });
        sectionLink.appendChild(el("div", { class: "org-agent-section-title", text: "关联信息" }));
        const latestTaskTitle = firstNonEmptyText([
          selectedAgentGraphNode && selectedAgentGraphNode.current_task_title,
        ], "");
        const latestTaskPath = firstNonEmptyText([
          selectedAgentGraphNode && selectedAgentGraphNode.current_task_path,
        ], "");
        const linkGrid = el("div", { class: "org-agent-kv-grid" });
        appendKV(linkGrid, "最近任务", latestTaskTitle || "-");
        appendKV(linkGrid, "任务路径", latestTaskPath || "-");
        appendKV(linkGrid, "最近Run", firstNonEmptyText([selectedAgentGraphNode && selectedAgentGraphNode.current_run_id], "-"));
        sectionLink.appendChild(linkGrid);
        if (peerLabelRows.length) {
          const peerWrap = el("div", { class: "org-agent-peer-list" });
          peerLabelRows.slice(0, 14).forEach((row) => {
            peerWrap.appendChild(chip(row.label, "muted"));
          });
          if (peerLabelRows.length > 14) peerWrap.appendChild(chip("+" + String(peerLabelRows.length - 14), "muted"));
          sectionLink.appendChild(peerWrap);
        }
        if (reasonList.length) {
          const reasonWrap = el("div", { class: "org-agent-reason-list" });
          reasonList.forEach(([reason, count]) => {
            reasonWrap.appendChild(chip(String(reason) + "×" + String(count), "muted"));
          });
          sectionLink.appendChild(reasonWrap);
        }
        agentPanel.appendChild(sectionLink);
      }
      stage.appendChild(agentPanel);

      if (manualPanelOpen) {
        const manualDraftMap = ORG_BOARD_UI.manualDraftByProject || (ORG_BOARD_UI.manualDraftByProject = Object.create(null));
        const draft = (manualDraftMap[pid] && typeof manualDraftMap[pid] === "object")
          ? manualDraftMap[pid]
          : {
              source_agent_id: selectedAgentId || "",
              target_agent_id: "",
              type_name: "",
              color: "",
            };
        manualDraftMap[pid] = draft;
        if (!draft.source_agent_id && selectedAgentId) draft.source_agent_id = selectedAgentId;
        const manualPanel = el("div", { class: "org-floating-manual-panel" });
        manualPanel.appendChild(el("div", { class: "org-manual-title", text: "人工关系管理" }));
        const row1 = el("div", { class: "org-manual-row" });
        const sourceSel = el("select", { class: "org-manual-input", title: "源Agent" });
        sourceSel.appendChild(el("option", { value: "", text: "选择源Agent" }));
        const targetSel = el("select", { class: "org-manual-input", title: "目标Agent" });
        targetSel.appendChild(el("option", { value: "", text: "选择目标Agent" }));
        allAgentNodes.forEach((row) => {
          const aid = String((row && row.agent_id) || "").trim();
          if (!aid) return;
          const label = normalizeOrgNodeLabel(row);
          sourceSel.appendChild(el("option", { value: aid, text: label + " · " + shortId(aid) }));
          targetSel.appendChild(el("option", { value: aid, text: label + " · " + shortId(aid) }));
        });
        sourceSel.value = String(draft.source_agent_id || "");
        targetSel.value = String(draft.target_agent_id || "");
        sourceSel.addEventListener("change", () => { draft.source_agent_id = String(sourceSel.value || ""); });
        targetSel.addEventListener("change", () => { draft.target_agent_id = String(targetSel.value || ""); });
        row1.appendChild(sourceSel);
        row1.appendChild(targetSel);
        manualPanel.appendChild(row1);

        const row2 = el("div", { class: "org-manual-row" });
        const typeInput = el("input", {
          class: "org-manual-input",
          type: "text",
          placeholder: "输入关系名称（如：协作/上下游/审核）",
          value: String(draft.type_name || ""),
        });
        typeInput.addEventListener("input", () => { draft.type_name = String(typeInput.value || ""); });
        const colorInput = el("input", {
          class: "org-manual-input org-manual-color",
          type: "color",
          value: String(draft.color || "#2f6fed"),
          title: "关系颜色",
        });
        colorInput.addEventListener("input", () => { draft.color = String(colorInput.value || ""); });
        row2.appendChild(typeInput);
        row2.appendChild(colorInput);
        manualPanel.appendChild(row2);

        const actionRow = el("div", { class: "org-manual-actions" });
        const addBtn = el("button", { class: "btn", type: "button", text: "新增关系" });
        addBtn.addEventListener("click", () => {
          try {
            const sourceAid = String(draft.source_agent_id || "").trim();
            const targetAid = String(draft.target_agent_id || "").trim();
            const typeName = String(draft.type_name || "").trim();
            if (!sourceAid || !targetAid || !typeName) {
              alert("请先选择源/目标Agent，并输入关系名称。");
              return;
            }
            const type = ensureOrgRelationTypeForProject(pid, typeName, String(draft.color || "").trim());
            if (!type) {
              alert("关系类型创建失败，请重试。");
              return;
            }
            addOrgManualRelation(pid, {
              source_agent_id: sourceAid,
              target_agent_id: targetAid,
              relation_type_id: String(type.id || ""),
            });
            ORG_BOARD_UI.noteByProject[pid] = "已新增人工关系：" + typeName;
            draft.type_name = "";
            render();
          } catch (e) {
            alert("新增关系失败：" + String((e && e.message) || e || "未知错误"));
          }
        });
        actionRow.appendChild(addBtn);
        const closePanelBtn = el("button", { class: "btn", type: "button", text: "收起" });
        closePanelBtn.addEventListener("click", () => {
          manualPanelOpenMap[pid] = false;
          render();
        });
        actionRow.appendChild(closePanelBtn);
        manualPanel.appendChild(actionRow);

        const manualList = el("div", { class: "org-manual-list" });
        if (!manualRelationsAll.length) {
          manualList.appendChild(el("div", { class: "task-schedule-empty", text: "当前项目暂无人工关系。" }));
        } else {
          manualRelationsAll
            .slice()
            .sort((a, b) => toTimeNum(String((b && b.updated_at) || "")) - toTimeNum(String((a && a.updated_at) || "")))
            .slice(0, 12)
            .forEach((rel) => {
              const typeId = String((rel && rel.relation_type_id) || "").trim();
              const tp = manualTypeById.get(typeId);
              const sourceRow = allAgentNodes.find((row) => String((row && row.agent_id) || "").trim() === String((rel && rel.source_agent_id) || "").trim());
              const targetRow = allAgentNodes.find((row) => String((row && row.agent_id) || "").trim() === String((rel && rel.target_agent_id) || "").trim());
              const row = el("div", { class: "org-manual-item" });
              row.appendChild(el("div", {
                class: "org-manual-item-main",
                text: (sourceRow ? normalizeOrgNodeLabel(sourceRow) : shortId(rel.source_agent_id)) + " → "
                  + (targetRow ? normalizeOrgNodeLabel(targetRow) : shortId(rel.target_agent_id)),
              }));
              const ops = el("div", { class: "org-manual-item-ops" });
              const typeChip = chip(String((tp && tp.name) || "关系"), "muted");
              if (tp && tp.color) {
                typeChip.style.borderColor = String(tp.color) + "66";
                typeChip.style.color = String(tp.color);
              }
              ops.appendChild(typeChip);
              const delBtn = el("button", { class: "btn", type: "button", text: "删除" });
              delBtn.addEventListener("click", () => {
                deleteOrgManualRelation(pid, rel.id);
                ORG_BOARD_UI.noteByProject[pid] = "已删除人工关系。";
                render();
              });
              ops.appendChild(delBtn);
              row.appendChild(ops);
              manualList.appendChild(row);
            });
        }
        manualPanel.appendChild(manualList);
        stage.appendChild(manualPanel);
      }

      if (allowManualEditing && linkEditor) {
        const editor = linkEditorMap[pid];
        const sourceAid = String((editor && editor.source_agent_id) || "").trim();
        const targetAid = String((editor && editor.target_agent_id) || "").trim();
        const sourceLabel = labelForAgentId(visibleNodes, sourceAid);
        const targetLabel = labelForAgentId(visibleNodes, targetAid);
        const editorPanel = el("div", { class: "org-link-editor-panel" });
        editorPanel.appendChild(el("div", { class: "org-manual-title", text: "创建直连关系" }));
        editorPanel.appendChild(el("div", {
          class: "org-link-editor-brief",
          text: sourceLabel + " → " + targetLabel,
        }));
        const rowType = el("div", { class: "org-manual-row" });
        const typeSel = el("select", { class: "org-manual-input", title: "选择已有关系类型" });
        typeSel.appendChild(el("option", { value: "", text: "选择已有关系类型（可选）" }));
        manualTypes.forEach((tp) => {
          const id = String((tp && tp.id) || "").trim();
          if (!id) return;
          typeSel.appendChild(el("option", { value: id, text: String(tp.name || "关系") }));
        });
        typeSel.value = String((editor && editor.relation_type_id) || "");
        typeSel.addEventListener("change", () => {
          const nextId = String(typeSel.value || "").trim();
          editor.relation_type_id = nextId;
          const row = nextId ? manualTypeById.get(nextId) : null;
          if (row) {
            editor.color = String(row.color || editor.color || "#2f6fed");
            editor.line_style = String(row.line_style || editor.line_style || "solid");
            editor.line_width = Number(row.line_width || editor.line_width || 4.2) || 4.2;
            editor.type_name = "";
          }
          render();
        });
        rowType.appendChild(typeSel);
        const typeInput = el("input", {
          class: "org-manual-input",
          type: "text",
          placeholder: "或输入新关系类型（如：主负责/依赖）",
          value: String((editor && editor.type_name) || ""),
        });
        typeInput.addEventListener("input", () => {
          editor.type_name = String(typeInput.value || "");
        });
        rowType.appendChild(typeInput);
        editorPanel.appendChild(rowType);

        const rowStyle = el("div", { class: "org-manual-row" });
        const lineStyleSel = el("select", { class: "org-manual-input", title: "线型" });
        lineStyleSel.appendChild(el("option", { value: "solid", text: "实线" }));
        lineStyleSel.appendChild(el("option", { value: "dash", text: "虚线" }));
        lineStyleSel.appendChild(el("option", { value: "dot", text: "点线" }));
        lineStyleSel.value = normalizeOrgRelationLineStyle(editor.line_style);
        lineStyleSel.addEventListener("change", () => {
          editor.line_style = normalizeOrgRelationLineStyle(lineStyleSel.value);
        });
        rowStyle.appendChild(lineStyleSel);
        const colorInput = el("input", {
          class: "org-manual-input org-manual-color",
          type: "color",
          title: "关系颜色",
          value: String(editor.color || "#2f6fed"),
        });
        colorInput.addEventListener("input", () => {
          editor.color = String(colorInput.value || "#2f6fed");
        });
        rowStyle.appendChild(colorInput);
        editorPanel.appendChild(rowStyle);

        const actionRow = el("div", { class: "org-manual-actions" });
        const confirmBtn = el("button", { class: "btn btn-primary", type: "button", text: "确认创建" });
        confirmBtn.addEventListener("click", () => submitLinkEditor());
        actionRow.appendChild(confirmBtn);
        const cancelBtn = el("button", { class: "btn", type: "button", text: "取消" });
        cancelBtn.addEventListener("click", () => {
          clearLinkDraft();
          clearLinkEditor();
          ORG_BOARD_UI.noteByProject[pid] = "已取消直连关系创建。";
          render();
        });
        actionRow.appendChild(cancelBtn);
        editorPanel.appendChild(actionRow);
        stage.appendChild(editorPanel);
      }

      const relCollapsed = !!(ORG_BOARD_UI.relCollapsedByProject && ORG_BOARD_UI.relCollapsedByProject[pid]);
      const relPanel = el("div", { class: "org-rel-panel org-floating-rel-panel" + (relCollapsed ? " collapsed" : "") });
      if (selectedAgentId) relPanel.classList.add("with-agent-panel");
      const relHead = el("div", { class: "org-rel-panel-head" });
      relHead.appendChild(el("div", { class: "org-rel-title", text: "运行态关系（最近）" }));
      const relOps = el("div", { class: "org-rel-panel-ops" });
      const relCountText = allowManualEditing
        ? ("运行态 " + visibleRelations.length + " 条 · 人工 " + visibleManualRelations.length + " 条")
        : ("运行态 " + visibleRelations.length + " 条");
      relOps.appendChild(chip(relCountText, "muted"));
      const foldBtn = el("button", { class: "btn", type: "button", text: relCollapsed ? "展开" : "收起" });
      foldBtn.addEventListener("click", () => {
        if (!ORG_BOARD_UI.relCollapsedByProject) ORG_BOARD_UI.relCollapsedByProject = Object.create(null);
        ORG_BOARD_UI.relCollapsedByProject[pid] = !relCollapsed;
        render();
      });
      relOps.appendChild(foldBtn);
      relHead.appendChild(relOps);
      relPanel.appendChild(relHead);

      if (!relCollapsed) {
        const relList = el("div", { class: "org-rel-list" });
        if (!visibleRelations.length && !visibleManualRelations.length) {
          relList.appendChild(el("div", { class: "task-schedule-empty", text: allowManualEditing ? "当前筛选下暂无关系。" : "当前筛选下暂无运行态关系。" }));
        } else {
          if (allowManualEditing) {
            visibleManualRelations
              .slice()
              .sort((a, b) => toTimeNum(String((b && b.updated_at) || "")) - toTimeNum(String((a && a.updated_at) || "")))
              .slice(0, 12)
              .forEach((rel) => {
                const srcAid = String((rel && rel.source_agent_id) || "").trim();
                const dstAid = String((rel && rel.target_agent_id) || "").trim();
                const typeRow = manualTypeById.get(String((rel && rel.relation_type_id) || "").trim());
                const from = labelForAgentId(nodes, srcAid);
                const to = labelForAgentId(nodes, dstAid);
                const row = el("div", { class: "org-rel-item active manual" });
                const left = el("div", { class: "org-rel-main", text: from + " ↔ " + to });
                const right = el("div", { class: "org-rel-meta" });
                const tp = chip(String((typeRow && typeRow.name) || "关系"), "good");
                if (typeRow && typeRow.color) {
                  tp.style.borderColor = String(typeRow.color) + "66";
                  tp.style.color = String(typeRow.color);
                  tp.style.background = String(typeRow.color) + "1A";
                }
                right.appendChild(tp);
                row.appendChild(left);
                row.appendChild(right);
                relList.appendChild(row);
              });
          }
          visibleRelations
            .slice()
            .sort((a, b) => toTimeNum(firstNonEmptyText([b && b.started_at, b && b.expires_at], "")) - toTimeNum(firstNonEmptyText([a && a.started_at, a && a.expires_at], "")))
            .slice(0, 20)
            .forEach((rel) => {
              const from = labelForRuntimeAgent(visibleNodes, rel, "source", agentLookup);
              const to = labelForRuntimeAgent(visibleNodes, rel, "target", agentLookup);
              const reason = String((rel && rel.reason) || "").trim() || "runtime";
              const due = compactDateTime(firstNonEmptyText([rel && rel.expires_at], ""));
              const row = el("div", { class: "org-rel-item" + (relationIsActive(rel) ? " active" : "") });
              const left = el("div", { class: "org-rel-main", text: from + " → " + to });
              const right = el("div", { class: "org-rel-meta" });
              right.appendChild(chip(reason, relationIsActive(rel) ? "good" : "muted"));
              if (due) right.appendChild(chip("到期:" + due, "muted"));
              row.appendChild(left);
              row.appendChild(right);
              relList.appendChild(row);
            });
        }
        relPanel.appendChild(relList);
      }
      stage.appendChild(relPanel);
    }

    function buildTaskModeList(listNode, barNode, mainMetaNode) {
      if (barNode) {
        barNode.innerHTML = "";
        barNode.style.display = "";
      }
      if (listNode) listNode.innerHTML = "";
      const groupsAll = buildTaskGroups(STATE.project);
      const lanes = taskLaneOrderList();
      const moduleMode = normalizeTaskModule(STATE.taskModule);
      const moduleLabel = moduleMode === "org" ? "组织" : "任务";
      const orgSnapshot = orgBoardSnapshot(STATE.project);
      const orgRuntime = orgBoardRuntime(STATE.project);
      const orgNodeCount = Array.isArray(orgSnapshot.nodes) ? orgSnapshot.nodes.length : 0;
      const orgRelCount = Array.isArray(orgRuntime.runtime_relations) ? orgRuntime.runtime_relations.length : 0;

      if (barNode) {
        const modeRow = el("div", { class: "filterrow" });
        modeRow.appendChild(chip("模块:" + moduleLabel, "muted"));
        modeRow.appendChild(chip("任务总数:" + groupsAll.length, groupsAll.length ? "good" : "muted"));
        modeRow.appendChild(chip("组织节点:" + orgNodeCount, orgNodeCount ? "good" : "muted"));
        modeRow.appendChild(chip("运行态关系:" + orgRelCount, orgRelCount ? "warn" : "muted"));
        barNode.appendChild(modeRow);
        if (moduleMode !== "org") {
          const laneRow = el("div", { class: "filterrow" });
          for (const lane of ["全部", ...lanes]) {
            laneRow.appendChild(chipButton(lane, STATE.taskLane === lane, () => {
              STATE.taskLane = lane;
              setHash();
              render();
            }));
          }
          barNode.appendChild(laneRow);
        }
      }

      if (moduleMode === "org") {
        buildOrgModeList(listNode, mainMetaNode, { view: "org" });
        return;
      }

      if (barNode) barNode.style.display = "none";
      buildTaskObservatoryModeList(listNode, groupsAll, mainMetaNode);
      return;

      const groups = STATE.taskLane === "全部"
        ? groupsAll
        : groupsAll.filter((g) => g.lane === STATE.taskLane);
      if (mainMetaNode) {
        mainMetaNode.textContent = "view=全项目任务聚合 · 总任务=" + groupsAll.length + " · 当前筛选=" + STATE.taskLane + " · generated_at=" + DATA.generated_at;
      }
      if (!groups.length) {
        listNode.appendChild(el("div", { class: "hint", text: "当前条件下没有匹配的总任务。" }));
        return;
      }

      for (const lane of lanes) {
        const laneGroups = groups.filter((g) => g.lane === lane);
        if (!laneGroups.length) continue;
        let laneGroupsRender = laneGroups.slice();
        let completedViewedCount = 0;
        let completedUnviewedCount = 0;
        if (lane === "已完成") {
          laneGroupsRender = laneGroups
            .slice()
            .sort((a, b) => {
              const aViewed = isTaskCompletedViewed(STATE.project, a && a.master && a.master.path, a && a.master && a.master.status);
              const bViewed = isTaskCompletedViewed(STATE.project, b && b.master && b.master.path, b && b.master && b.master.status);
              if (aViewed !== bViewed) return aViewed ? 1 : -1;
              return Number(b.latestTs || -1) - Number(a.latestTs || -1);
            });
          for (const g of laneGroupsRender) {
            const viewed = isTaskCompletedViewed(STATE.project, g && g.master && g.master.path, g && g.master && g.master.status);
            if (viewed) completedViewedCount += 1;
            else completedUnviewedCount += 1;
          }
        }
        const laneSec = el("section", { class: "task-lane" + ((STATE.taskLaneCollapsed[lane] && (lane === "已完成" || lane === "已归档")) ? " collapsed" : "") });
        const laneHead = el("div", { class: "task-lane-head" });
        const laneTitle = el("div", { class: "task-lane-title" });
        laneTitle.appendChild(chip(lane, taskLaneTone(lane) + (lane === "已归档" ? " archived-tag" : "")));
        laneTitle.appendChild(el("span", { text: "总任务 " + laneGroupsRender.length }));
        if (lane === "已完成") {
          laneTitle.appendChild(chip("未看:" + completedUnviewedCount, completedUnviewedCount ? "warn" : "muted"));
          laneTitle.appendChild(chip("已看:" + completedViewedCount, completedViewedCount ? "good" : "muted"));
        }
        laneHead.appendChild(laneTitle);
        if (lane === "已完成" || lane === "已归档") {
          const collapseBtn = el("button", { class: "btn", text: STATE.taskLaneCollapsed[lane] ? "展开" : "收起", type: "button" });
          collapseBtn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            toggleTaskLaneCollapse(lane);
          });
          laneHead.appendChild(collapseBtn);
        }
        laneSec.appendChild(laneHead);

        const laneBody = el("div", { class: "task-lane-body" });
        for (const g of laneGroupsRender) {
          const master = g.master || (g.children[0] || null);
          if (!master) continue;
          const selectedPath = String(STATE.selectedPath || "");
          const selectedTaskId = normalizeTaskStableId(STATE.selectedTaskId || "");
          const masterPath = String(master.path || "");
          const masterTaskId = taskStableIdOfItem(master);
          const doneViewed = lane === "已完成"
            ? isTaskCompletedViewed(STATE.project, masterPath, master && master.status)
            : false;
          const sourceMode = "active";
          const visibleChildren = (Array.isArray(g.children) ? g.children : []).filter((child) => taskChildMatchesSource(child, sourceMode));
          const hasChildSelected = Array.isArray(g.children)
            ? g.children.some((c) => taskSelectionMatchesItem(c, selectedPath, selectedTaskId))
            : false;
          const groupCard = el("div", {
            class: "frow task-group-card" + ((taskSelectionMatchesItem(master, selectedPath, selectedTaskId) || hasChildSelected) ? " active" : ""),
            "data-path": masterPath,
          });
          if (lane === "已归档") groupCard.classList.add("is-archived");
          if (lane === "已完成" && !doneViewed) groupCard.classList.add("is-completed-unviewed");
          const scheduled = isTaskScheduledByItem(master);
          if (scheduled) groupCard.classList.add("is-scheduled");
          bindTaskScheduleDragSource(groupCard, master);
          const head = el("div", { class: "task-group-head" });
          head.appendChild(buildItemTitleNode(master, "t"));
          const headOps = el("div", { class: "frow-title-ops" });
          if (lane === "已完成") {
            const viewedBtn = el("button", {
              class: "btn" + (doneViewed ? " btn-soft-good" : ""),
              type: "button",
              text: doneViewed ? "已查看" : "标记已查看",
              title: doneViewed ? "已标记为已查看，点击可撤销" : "将该完成任务标记为已查看",
            });
            viewedBtn.addEventListener("click", (e) => {
              e.preventDefault();
              e.stopPropagation();
              setTaskCompletedViewed(STATE.project, masterPath, !doneViewed);
              render();
            });
            headOps.appendChild(viewedBtn);
          }
          const scheduleBtn = createTaskScheduleToggleBtn(master, true);
          if (scheduleBtn) headOps.appendChild(scheduleBtn);
          const pushBtn = createTaskPushEntryBtn(master, true);
          if (pushBtn) headOps.appendChild(pushBtn);
          head.appendChild(headOps);
          groupCard.appendChild(head);

          const statusMeta = el("div", { class: "m" });
          const masterFlags = taskStatusFlags(master);
          statusMeta.appendChild(chip("主任务状态:" + g.masterBucket, taskPrimaryTone(g.masterBucket)));
          if (masterFlags.supervised) statusMeta.appendChild(chip("关注", "bad"));
          if (masterFlags.blocked) statusMeta.appendChild(chip("阻塞", "bad"));
          if (lane === "已完成") {
            statusMeta.appendChild(chip(doneViewed ? "已查看" : "未查看", doneViewed ? "good" : "warn"));
          }
          statusMeta.appendChild(chip("所属通道:" + resolveTaskGroupChannel(g), "muted"));
          statusMeta.appendChild(chip("子任务总数:" + g.childTotal, "muted"));
          statusMeta.appendChild(chip("子任务显示:" + visibleChildren.length + "/" + g.children.length, "muted"));
          const order = ["进行中", "待办", "待验收", "已完成", "暂缓"];
          for (const k of order) {
            const c = Number(g.childCounts[k] || 0);
            if (!c) continue;
            statusMeta.appendChild(chip(k + ":" + c, toneForBucket(k)));
          }
          if (g.latestAt) statusMeta.appendChild(chip("更新:" + g.latestAt, "muted"));
          groupCard.appendChild(statusMeta);

          const summaryText = visibleChildren.length
            ? taskGroupSummaryText(g, visibleChildren)
            : "当前暂无可展示子任务。";
          groupCard.appendChild(el("div", { class: "task-group-summary", text: summaryText }));

          const expanded = !!STATE.taskGroupExpanded[g.key];
          const foldBtn = el("button", { class: "btn", type: "button", text: expanded ? "收起子任务" : ("展开子任务（" + visibleChildren.length + "）") });
          if (!visibleChildren.length) foldBtn.disabled = true;
          foldBtn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            toggleTaskGroupExpanded(g.key);
          });
          groupCard.appendChild(foldBtn);

          if (expanded) {
            const childWrap = el("div", { class: "task-group-children" });
            if (!visibleChildren.length) {
              childWrap.appendChild(el("div", { class: "task-group-empty", text: "当前筛选条件下暂无子任务。" }));
            }
            for (const child of visibleChildren) {
              const childPath = String((child && child.path) || "");
              const row = el("div", {
                class: "task-group-child" + (taskSelectionMatchesItem(child, selectedPath, selectedTaskId) ? " active" : ""),
                "data-path": childPath,
              });
              const left = el("div", { style: "min-width:0;flex:1;" });
              left.appendChild(el("div", { class: "task-group-child-title", text: shortTitle(child.title || "") }));
              const cm = el("div", { class: "task-group-child-meta" });
              cm.appendChild(chip(bucketKeyForStatus(child.status), toneForBucket(bucketKeyForStatus(child.status))));
              if (child.channel) cm.appendChild(chip(child.channel, "muted"));
              if (child.updated_at) cm.appendChild(chip("更新:" + child.updated_at, "muted"));
              left.appendChild(cm);
              row.appendChild(left);
              const right = el("div", { class: "frow-title-ops" });
              const cpb = createTaskPushEntryBtn(child, true);
              if (cpb) right.appendChild(cpb);
              row.appendChild(right);
              row.addEventListener("click", (e) => {
                e.preventDefault();
                e.stopPropagation();
                setSelectedTaskRef(child.path, taskStableIdOfItem(child));
              });
              childWrap.appendChild(row);
            }
            groupCard.appendChild(childWrap);
          }

          bindCardSelectSemantics(groupCard, () => {
            setSelectedTaskRef(master.path, masterTaskId);
          });
          laneBody.appendChild(groupCard);
        }
        laneSec.appendChild(laneBody);
        listNode.appendChild(laneSec);
      }
    }
