    function createConversationLocalAttachmentId(seed = "") {
      const prefix = String(seed || "").trim() || "local-att";
      return prefix + "-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8);
    }

    function normalizeConversationAttachmentObject(att, opts = {}) {
      const src = (att && typeof att === "object") ? att : {};
      const localId = String(src.localId || src.local_id || (opts && opts.localId) || "").trim();
      const filename = String(src.filename || "").trim();
      const originalName = String(src.originalName || src.original_name || filename || "attachment").trim();
      const url = String(src.url || src.href || "").trim();
      const dataUrl = String(src.dataUrl || src.data_url || "").trim();
      const mimeType = String(src.mimeType || src.mime_type || "").trim();
      const status = String(src.uploadState || src.upload_state || src.status || (url || dataUrl ? "ready" : "uploading")).trim() || "ready";
      return {
        localId,
        filename,
        originalName,
        url,
        dataUrl,
        mimeType,
        size: Math.max(0, Number(src.size || 0) || 0),
        isImage: !!(src.isImage || mimeType.indexOf("image/") === 0 || /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(originalName)),
        uploadState: status,
        uploadError: String(src.uploadError || src.upload_error || "").trim(),
        confirmedAt: String(src.confirmedAt || src.confirmed_at || "").trim(),
        updatedAt: String(src.updatedAt || src.updated_at || conversationStoreNowIso()),
      };
    }

    function recordConversationAttachment(projectId, sessionId, attachment, opts = {}) {
      const normalized = normalizeConversationAttachmentObject(attachment, opts);
      if (!normalized.localId && !normalized.filename && !normalized.url) return null;
      return conversationStoreUpsertAttachment(projectId, sessionId, normalized, opts);
    }

    function recordConversationAttachments(projectId, sessionId, attachments, opts = {}) {
      return (Array.isArray(attachments) ? attachments : [])
        .map((attachment) => recordConversationAttachment(projectId, sessionId, attachment, opts))
        .filter(Boolean);
    }

    function mapComposerAttachmentsForSend(projectId, sessionId, attachments, opts = {}) {
      return (Array.isArray(attachments) ? attachments : [])
        .map((attachment) => {
          const normalized = normalizeConversationAttachmentObject(attachment, opts);
          recordConversationAttachment(projectId, sessionId, normalized, {
            ...(opts || {}),
            source: String((opts && opts.source) || "composer-send"),
          });
          return {
            filename: normalized.filename,
            originalName: normalized.originalName,
            url: normalized.url || normalized.dataUrl || "",
            local_id: normalized.localId,
          };
        });
    }
