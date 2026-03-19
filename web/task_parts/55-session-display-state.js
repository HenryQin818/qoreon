    function normalizeSessionDisplayState(raw, fallback = "idle") {
      return normalizeDisplayState(raw, fallback);
    }

    function normalizeLatestRunSummary(raw) {
      const src = (raw && typeof raw === "object") ? raw : {};
      return {
        run_id: String(firstNonEmptyText([src.run_id, src.runId]) || "").trim(),
        status: normalizeSessionDisplayState(firstNonEmptyText([src.status, src.display_state, src.displayState]), "idle"),
        updated_at: String(firstNonEmptyText([src.updated_at, src.updatedAt, src.finished_at, src.finishedAt, src.created_at, src.createdAt]) || "").trim(),
        preview: String(firstNonEmptyText([src.preview, src.last_preview, src.lastPreview]) || "").trim(),
        speaker: String(firstNonEmptyText([src.speaker, src.last_speaker, src.lastSpeaker]) || "assistant").trim() || "assistant",
        sender_type: String(firstNonEmptyText([src.sender_type, src.senderType, src.last_sender_type, src.lastSenderType]) || "").trim(),
        sender_name: String(firstNonEmptyText([src.sender_name, src.senderName, src.last_sender_name, src.lastSenderName]) || "").trim(),
        sender_source: String(firstNonEmptyText([src.sender_source, src.senderSource, src.last_sender_source, src.lastSenderSource]) || "").trim(),
        latest_user_msg: String(firstNonEmptyText([src.latest_user_msg, src.latestUserMsg]) || "").trim(),
        latest_ai_msg: String(firstNonEmptyText([src.latest_ai_msg, src.latestAiMsg]) || "").trim(),
        error: String(firstNonEmptyText([src.error, src.last_error, src.lastError]) || "").trim(),
        run_count: Math.max(0, Number(firstNonEmptyText([src.run_count, src.runCount, 0])) || 0),
      };
    }

    function getSessionLatestRunSummary(session) {
      const s = (session && typeof session === "object") ? session : {};
      return normalizeLatestRunSummary(s.latest_run_summary || s.latestRunSummary || null);
    }

    function getSessionDisplayState(session) {
      const s = (session && typeof session === "object") ? session : {};
      const raw = firstNonEmptyText([
        s.session_display_state,
        s.sessionDisplayState,
      ]);
      if (raw) return normalizeSessionDisplayState(raw, "idle");
      const runtimeState = getSessionRuntimeState(s);
      return normalizeSessionDisplayState(runtimeState.display_state, "idle");
    }

    function getSessionDisplayReason(session) {
      const s = (session && typeof session === "object") ? session : {};
      return String(firstNonEmptyText([s.session_display_reason, s.sessionDisplayReason]) || "").trim();
    }

    function isLatestRunSummaryTerminal(summary) {
      const latest = normalizeLatestRunSummary(summary);
      return latest.status === "done" || latest.status === "error";
    }

    function latestRunSummaryUpdatedAt(session) {
      return String(getSessionLatestRunSummary(session).updated_at || "").trim();
    }
