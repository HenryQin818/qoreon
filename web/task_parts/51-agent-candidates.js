    const PROJECT_AGENT_CANDIDATE_CACHE = Object.create(null);
    const PROJECT_AGENT_CANDIDATE_TTL_MS = 15_000;

    async function fetchProjectAgentTargetRows(projectId, force = false) {
      const pid = String(projectId || "").trim();
      if (!pid || pid === "overview") {
        return { rows: [], error: "", source: "", count: 0 };
      }

      const now = Date.now();
      const cached = PROJECT_AGENT_CANDIDATE_CACHE[pid];
      if (
        !force
        && cached
        && Array.isArray(cached.rows)
        && (now - Number(cached.fetchedAt || 0) < PROJECT_AGENT_CANDIDATE_TTL_MS)
      ) {
        return {
          rows: cached.rows.slice(),
          error: String(cached.error || ""),
          source: String(cached.source || ""),
          count: Number(cached.count || cached.rows.length || 0),
        };
      }

      let rows = [];
      let error = "";
      let source = "";
      let count = 0;

      try {
        const r = await fetch("/api/agent-candidates?project_id=" + encodeURIComponent(pid), {
          cache: "no-store",
          headers: authHeaders(),
        });
        const j = await r.json().catch(() => ({}));
        if (r.ok && j && typeof j === "object" && Array.isArray(j.agent_targets)) {
          rows = j.agent_targets;
          source = String(j.source || "session_store_recommended");
          count = Number(j.count || j.agent_targets.length || 0);
        } else if (!r.ok) {
          error = String((j && (j.error || j.message)) || "加载 Agent 候选失败");
        }
      } catch (err) {
        error = String((err && err.message) || "加载 Agent 候选失败");
      }

      if (!rows.length) {
        try {
          const r = await fetch("/api/sessions?project_id=" + encodeURIComponent(pid), {
            cache: "no-store",
            headers: authHeaders(),
          });
          const j = await r.json().catch(() => ({}));
          if (r.ok && j && typeof j === "object" && Array.isArray(j.sessions)) {
            rows = j.sessions;
            source = "sessions_fallback";
            count = Number(j.sessions.length || 0);
            error = "";
          } else if (!error && !r.ok) {
            error = String((j && (j.error || j.message)) || "加载 Agent 候选失败");
          }
        } catch (err) {
          if (!error) error = String((err && err.message) || "加载 Agent 候选失败");
        }
      }

      PROJECT_AGENT_CANDIDATE_CACHE[pid] = {
        rows: Array.isArray(rows) ? rows.slice() : [],
        error,
        source,
        count,
        fetchedAt: now,
      };
      return {
        rows: Array.isArray(rows) ? rows.slice() : [],
        error,
        source,
        count,
      };
    }
