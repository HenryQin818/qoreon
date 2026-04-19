    // task.js 第二刀：Codex run API 与增量游标口径
    async function apiHealth() {
      const j = await fetchHealthInfo();
      return !!(j && j.ok);
    }

    function taskDashboardCodexApiReadState() {
      const root = (typeof window !== "undefined" && window) ? window : globalThis;
      if (!root.__taskDashboardCodexApiReadState || typeof root.__taskDashboardCodexApiReadState !== "object") {
        root.__taskDashboardCodexApiReadState = {
          runsPromiseByUrl: Object.create(null),
          runPromiseById: Object.create(null),
        };
      }
      return root.__taskDashboardCodexApiReadState;
    }

    async function loadRuns(params = {}) {
      const qs = new URLSearchParams();
      qs.set("limit", String(params.limit || 30));
      if (params.channelId) qs.set("channelId", String(params.channelId));
      if (params.projectId) qs.set("projectId", String(params.projectId));
      if (params.sessionId) qs.set("sessionId", String(params.sessionId));
      if (params.afterCreatedAt) qs.set("afterCreatedAt", String(params.afterCreatedAt));
      if (params.beforeCreatedAt) qs.set("beforeCreatedAt", String(params.beforeCreatedAt));
      if (params.payloadMode) qs.set("payloadMode", String(params.payloadMode));
      const url = "/api/codex/runs?" + qs.toString();
      const state = taskDashboardCodexApiReadState();
      if (state.runsPromiseByUrl[url]) return state.runsPromiseByUrl[url];
      state.runsPromiseByUrl[url] = (async () => {
        const r = await fetch(url, { cache: "no-store" });
        if (!r.ok) throw new Error("runs fetch failed");
        return await r.json();
      })().finally(() => {
        delete state.runsPromiseByUrl[url];
      });
      return state.runsPromiseByUrl[url];
    }

    function runsLatestCreatedAt(runs) {
      const src = Array.isArray(runs) ? runs : [];
      let latestTs = -1;
      let latestText = "";
      for (const r of src) {
        const txt = String((r && r.createdAt) || "").trim();
        if (!txt) continue;
        const ts = toTimeNum(txt);
        if (ts > latestTs) {
          latestTs = ts;
          latestText = txt;
        }
      }
      return latestText;
    }

    function formatUtcSecondCursor(tsMs) {
      const ms = Number(tsMs);
      if (!Number.isFinite(ms)) return "";
      const d = new Date(ms);
      if (Number.isNaN(d.getTime())) return "";
      const pad2 = (n) => String(Math.max(0, Number(n) || 0)).padStart(2, "0");
      return [
        d.getUTCFullYear(),
        "-",
        pad2(d.getUTCMonth() + 1),
        "-",
        pad2(d.getUTCDate()),
        "T",
        pad2(d.getUTCHours()),
        ":",
        pad2(d.getUTCMinutes()),
        ":",
        pad2(d.getUTCSeconds()),
        "+0000",
      ].join("");
    }

    function incrementalAfterCursorWithOverlap(runs, overlapMs = 1000) {
      const latestText = runsLatestCreatedAt(runs);
      if (!latestText) return "";
      const latestTs = toTimeNum(latestText);
      if (latestTs < 0) return latestText;
      const safeOverlap = Math.max(0, Number(overlapMs) || 0);
      return formatUtcSecondCursor(Math.max(0, latestTs - safeOverlap)) || latestText;
    }

    function runsOldestCreatedAt(runs) {
      const src = Array.isArray(runs) ? runs : [];
      let oldestTs = Number.POSITIVE_INFINITY;
      let oldestText = "";
      for (const r of src) {
        const txt = String((r && r.createdAt) || "").trim();
        if (!txt) continue;
        const ts = toTimeNum(txt);
        if (ts < 0) continue;
        if (ts < oldestTs) {
          oldestTs = ts;
          oldestText = txt;
        }
      }
      if (oldestText) return oldestText;
      let fallback = "";
      for (const r of src) {
        const txt = String((r && r.createdAt) || "").trim();
        if (!txt) continue;
        if (!fallback || txt < fallback) fallback = txt;
      }
      return fallback;
    }

    function runSnapshotProgressTs(run) {
      const src = (run && typeof run === "object") ? run : {};
      return Math.max(
        toTimeNum(firstNonEmptyText([
          src.lastProgressAt,
          src.updatedAt,
          src.updated_at,
          src.startedAt,
          src.started_at,
          src.createdAt,
        ])),
        -1
      );
    }

    function runSnapshotFinishedTs(run) {
      const src = (run && typeof run === "object") ? run : {};
      return Math.max(
        toTimeNum(firstNonEmptyText([
          src.finishedAt,
          src.finished_at,
        ])),
        -1
      );
    }

    function isWorkingLikeRunStateForMerge(st) {
      const s = String(st || "").trim().toLowerCase();
      return isRunWorking(s) || s === "external_busy";
    }

    function isTerminalLikeRunStateForMerge(st) {
      const s = String(st || "").trim().toLowerCase();
      return s === "done" || s === "error" || s === "interrupted";
    }

    function mergeRunSnapshot(existingRun, incomingRun) {
      const prev = (existingRun && typeof existingRun === "object") ? existingRun : {};
      const next = (incomingRun && typeof incomingRun === "object") ? incomingRun : {};
      const prevState = String(getRunDisplayState(prev, null) || prev.status || "").trim().toLowerCase();
      const nextState = String(getRunDisplayState(next, null) || next.status || "").trim().toLowerCase();
      const prevWorking = isWorkingLikeRunStateForMerge(prevState);
      const nextWorking = isWorkingLikeRunStateForMerge(nextState);
      const prevTerminal = isTerminalLikeRunStateForMerge(prevState);
      const nextTerminal = isTerminalLikeRunStateForMerge(nextState);
      const prevProgressTs = runSnapshotProgressTs(prev);
      const nextProgressTs = runSnapshotProgressTs(next);
      const prevFinishedTs = runSnapshotFinishedTs(prev);
      const nextFinishedTs = runSnapshotFinishedTs(next);
      const merged = { ...prev, ...next };

      // 同一 runId 的状态只能单向流转到终态；一旦服务端新快照已是终态，
      // 不要再把页面内旧的 working 快照保留下来，否则会出现
      // “正文已完成但状态仍显示处理中/执行异常，刷新后才正常”的错位。
      if (prevWorking && nextTerminal) {
        return merged;
      }

      // 同理，若页面已经拿到终态，不允许后续乱序/滞后的 working 快照把它压回去。
      if (prevTerminal && nextWorking) {
        return { ...merged, ...prev };
      }

      if (prevTerminal && nextTerminal && prevFinishedTs > nextFinishedTs && prevFinishedTs >= 0) {
        return { ...merged, ...prev };
      }
      return merged;
    }

    function mergeRunsById(existingRuns, incomingRuns, maxKeep = 400) {
      const merged = new Map();
      const append = (list) => {
        const src = Array.isArray(list) ? list : [];
        for (const r of src) {
          const id = String((r && r.id) || "").trim();
          if (!id) continue;
          const prev = merged.get(id);
          merged.set(id, prev ? mergeRunSnapshot(prev, r) : r);
        }
      };
      append(existingRuns);
      append(incomingRuns);
      const out = Array.from(merged.values());
      out.sort((a, b) => {
        const ta = toTimeNum(a && a.createdAt);
        const tb = toTimeNum(b && b.createdAt);
        if (ta >= 0 && tb >= 0 && ta !== tb) return tb - ta;
        return String((b && b.createdAt) || "").localeCompare(String((a && a.createdAt) || ""));
      });
      return out.slice(0, Math.max(40, Number(maxKeep) || 400));
    }

    function hasWorkingRun(runs) {
      const src = Array.isArray(runs) ? runs : [];
      return src.some((r) => {
        const rid = String((r && r.id) || "").trim();
        const detail = (rid && typeof PCONV !== "undefined" && PCONV && PCONV.detailMap)
          ? (PCONV.detailMap[rid] || null)
          : null;
        return isRunWorking(getRunDisplayState(r, detail));
      });
    }

    async function loadRun(id) {
      const runId = String(id || "").trim();
      const state = taskDashboardCodexApiReadState();
      if (state.runPromiseById[runId]) return state.runPromiseById[runId];
      state.runPromiseById[runId] = (async () => {
        const r = await fetch("/api/codex/run/" + encodeURIComponent(runId), { cache: "no-store" });
        if (!r.ok) throw new Error("run fetch failed");
        return await r.json();
      })().finally(() => {
        delete state.runPromiseById[runId];
      });
      return state.runPromiseById[runId];
    }

    async function callRunAction(runId, action) {
      const rid = String(runId || "").trim();
      const act = String(action || "").trim();
      if (!rid || !act) throw new Error("invalid run action");
      const r = await fetch("/api/codex/run/" + encodeURIComponent(rid) + "/action", {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ action: act }),
      });
      if (!r.ok) {
        const detail = await parseResponseDetail(r);
        throw new Error(detail || ("HTTP " + r.status));
      }
      return await r.json().catch(() => ({}));
    }
